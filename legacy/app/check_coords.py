"""
check_coords.py — verify (and optionally fix) the coordinates of every
enriched surf break in data/australia-surf-breaks-enriched.json.

Two phases:

1. CHECK (free, no API calls) — deterministic sanity checks per break:
   - invalid:        coords missing or not finite numbers
   - out_of_australia: lat/lng outside Australia's bounding box
   - wrong_state:    lat/lng outside the break's own state bounding box
   - duplicate:      same point (within 0.005 deg) as a *different* break —
                     a common LLM failure mode is copying the nearest town
                     centre or another break's coordinates
   - region_outlier: > REGION_OUTLIER_KM from the median of its
                     (state, region) cluster

2. FIX (--fix) — for each flagged break, look the spot up in
   OpenStreetMap via Nominatim (the same data the UI map renders, so the
   marker lands exactly on the feature). The best candidate must pass the
   deterministic checks above (in Australia, in the right state, not a
   duplicate) before it is accepted. Spots OSM doesn't know can fall back
   to a focused LLM estimate with --source llm or --source both.
   A timestamped backup of the file is written before the first change;
   the file is saved after every accepted fix.

Usage:
    uv run python app/check_coords.py            # report only (no network)
    uv run python app/check_coords.py --fix      # fix hard failures via OSM (no API key needed)
    uv run python app/check_coords.py --fix --all  # also fix region outliers
    uv run python app/check_coords.py --fix --source both --max-fixes 10
    # --source both additionally needs HF_TOKEN for the LLM fallback.
"""

import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from huggingface_hub import InferenceClient

try:  # package import from repo root
    from legacy.app.generate_surf_break import MODEL_ID, PROVIDER, extract_json
except ImportError:  # pragma: no cover — standalone fallback
    MODEL_ID = "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16"
    PROVIDER = "deepinfra"

    def extract_json(text: str) -> dict:  # type: ignore[no-redef]
        text = text.strip()
        fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.E | re.S)
        if fence:
            text = fence.group(1)
        else:
            brace = re.search(r"\{.*\}", text, re.E | re.S)
            text = brace.group(0)
        return json.loads(text)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
ENRICHED_FILE = DATA_DIR / "australia-surf-breaks-enriched.json"

REQUEST_DELAY = 1.0  # seconds between inference calls
MAX_RETRIES = 2

# Rough bounding boxes (lat_min, lat_max, lng_min, lng_max) per state.
# Good enough to catch a break dropped in the wrong state/territory.
AUSTRALIA_BOX = (-44.5, -8.5, 109.5, 156.5)
STATE_BOXES = {
    "Western Australia": (-50.5, -10.7, 112.5, 129.3),
    "Northern Territory": (-26.6, -10.6, 129.0, 138.2),
    "Queensland": (-43.8, -10.6, 135.5, 154.0),
    "South Australia": (-39.1, -25.8, 129.0, 141.1),
    # NSW/QLD border runs along 28.5S out to the coast at ~153.63E (Cape Byron);
    # NSW/SA border is the 141E meridian.
    "New South Wales": (-39.1, -28.0, 140.9, 153.65),
    "Victoria": (-39.3, -33.9, 140.9, 150.2),
    "Tasmania": (-43.8, -40.4, 143.4, 149.6),
    "ACT": (-36.0, -35.2, 148.6, 149.5),
}

DUP_RADIUS_DEG = 0.005  # ~0.55 km — effectively "same point"
REGION_OUTLIER_KM = 100.0


# ---------------------------------------------------------------- checks

def _coords(break_: dict) -> tuple[float, float] | None:
    try:
        lat = float(break_["location"]["coordinates"]["lat"])
        lng = float(break_["location"]["coordinates"]["lng"])
        if not (math.isfinite(lat) and math.isfinite(lng)):
            return None
        return lat, lng
    except (KeyError, TypeError, ValueError):
        return None


def _in_box(lat: float, lng: float, box: tuple) -> bool:
    lat_min, lat_max, lng_min, lng_max = box
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def check_point(lat: float, lng: float, state: str, other_points: list[tuple[float, float]]) -> list[str]:
    """Run the deterministic checks for one (lat, lng) against one state.

    ``other_points`` are the coordinates of the *other* breaks (already
    placed), used for the duplicate check. Returns a list of reason tags
    (empty == passes).
    """
    reasons: list[str] = []
    if not _in_box(lat, lng, AUSTRALIA_BOX):
        reasons.append("out_of_australia")
    box = STATE_BOXES.get(state)
    if box and not _in_box(lat, lng, box):
        reasons.append("wrong_state")
    for o_lat, o_lng in other_points:
        if abs(lat - o_lat) < DUP_RADIUS_DEG and abs(lng - o_lng) < DUP_RADIUS_DEG:
            reasons.append("duplicate")
            break
    return reasons


def check_all(breaks: list[dict]) -> list[dict]:
    """Check every break; returns [{break, coords, reasons}] for flagged ones."""
    points = {id(b): _coords(b) for b in breaks}
    flagged = []

    # Region medians (per state+region cluster) for the outlier check.
    clusters: dict[tuple, list[tuple[float, float]]] = defaultdict(list)
    for b in breaks:
        p = points[id(b)]
        if p:
            clusters[(b.get("state", ""), b.get("region", ""))].append(p)
    medians = {}
    for key, pts in clusters.items():
        medians[key] = (
            sorted(p[0] for p in pts)[len(pts) // 2],
            sorted(p[1] for p in pts)[len(pts) // 2],
        )

    for b in breaks:
        p = points[id(b)]
        reasons: list[str] = []
        if p is None:
            reasons.append("invalid")
        else:
            others = [
                points[id(o)]
                for o in breaks
                if o is not b and (points[id(o)] is not None)
            ]
            reasons.extend(check_point(p[0], p[1], b.get("state", ""), others))
            med = medians.get((b.get("state", ""), b.get("region", "")))
            if med and _haversine_km(p, med) > REGION_OUTLIER_KM:
                reasons.append("region_outlier")
        if reasons:
            flagged.append({"break": b, "coords": p, "reasons": reasons})
    return flagged


# ---------------------------------------------------------------- fix

# OpenStreetMap (Nominatim) is the ground-truth source: the UI map renders
# OSM tiles, so a point taken from OSM sits exactly on the feature shown.
# Usage policy: <=1 request/second, descriptive User-Agent, no caching needed
# for a one-off maintenance run.
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_UA = "wavereader-coord-check/1.0 (one-off surf-break data maintenance)"
_nominatim_last_call = 0.0

# Score bonuses for candidate feature kinds: we want the physical spot
# (beach/reef/river mouth), not the suburb it happens to be inside.
_TYPE_SCORE = {
    "beach": 6, "reef": 6, "bay": 5, "water": 5, "shoreline": 5, "cove": 5,
    "coastline": 4, "headland": 4, "cape": 4, "point": 4, "rock": 3,
    "bare_rock": 3, "strait": 3, "harbour": 2, "island": 2, "river": 3,
    "stream": 3, "estuary": 3, "blowhole": 3, "attraction": 2, "viewpoint": 2,
}
_CLASS_SCORE = {"natural": 3, "waterway": 3, "man_made": 1, "tourism": 2}

# Feature kinds that can never be a surf takeoff zone.
_NEVER_CLASSES = {"highway", "rail", "industrial", "commercial", "amenity",
                  "landuse", "building", "military", "power"}
_NEVER_TYPES = {"road", "footway", "cycleway", "path", "track", "house",
                "building", "site", "information"}
# Physical water/land features — trusted on name match alone.
_PHYSICAL_TYPES = set(_TYPE_SCORE)
# Settlements / postal localities — accepted only when unambiguous.
_PLACE_TYPES = {"town", "village", "hamlet", "locality", "administrative",
                "suburb", "city", "neighbourhood", "isolated_dwelling"}


def _pace_nominatim() -> None:
    global _nominatim_last_call
    wait = 1.05 - (time.time() - _nominatim_last_call)
    if wait > 0:
        time.sleep(wait)
    _nominatim_last_call = time.time()


def nominatim_search(query: str, limit: int = 5) -> list[dict]:
    """One Nominatim free-form search, Australia-only, paced to 1 req/s."""
    _pace_nominatim()
    url = NOMINATIM_URL + "?" + urllib.parse.urlencode(
        {"q": query, "format": "jsonv2", "limit": limit, "countrycodes": "au"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": NOMINATIM_UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _candidate_kind(cand: dict) -> str | None:
    """Classify a Nominatim hit: 'physical', 'place', or None (never accept)."""
    cls, typ = cand.get("class") or "", cand.get("type") or ""
    if cls in _NEVER_CLASSES or typ in _NEVER_TYPES:
        return None
    if "council" in cand.get("display_name", "").lower():
        return None  # council boundary centroids are useless
    if typ in _PHYSICAL_TYPES or cls in ("natural", "waterway"):
        return "physical"
    if typ in _PLACE_TYPES or cls == "place":
        return "place"
    return "place"  # unknown feature kinds: treat conservatively


def _candidate_score(cand: dict, anchor: tuple[float, float] | None) -> float:
    lat, lng = float(cand["lat"]), float(cand["lon"])
    score = _TYPE_SCORE.get(cand.get("type", ""), 1) + _CLASS_SCORE.get(cand.get("class", ""), 0)
    if anchor is not None:  # prefer the candidate nearest the region's trusted cluster
        score -= 0.05 * _haversine_km((lat, lng), anchor)
    return score


def osm_match(
    break_: dict,
    state: str,
    anchor: tuple[float, float] | None,
    current: tuple[float, float] | None,
    hard_fail: bool,
) -> tuple[float, float, str] | None:
    """Geocode one break against OSM. Returns (lat, lng, display_name) of the
    chosen candidate, or None to keep the existing coordinates.

    Trust model:
    - a *physical* feature (beach/bay/cape/river mouth/...) with a name match
      is accepted outright, unless the existing point is clearly closer to
      the region's trusted cluster (G2 veto — guards against same-name
      features elsewhere in the state, e.g. two different 'Fishery Bays');
    - a *settlement* (town/hamlet/locality/boundary) is accepted only when it
      is the sole viable candidate or the existing point is the one far from
      the cluster — never when it just happens to be the nearest hit;
    - highways, roads, viewpoints and council centroids are never accepted.

    ``hard_fail``: the existing point failed a hard check (invalid/outside
    Australia/wrong state) — it is untrusted, so the G2 veto does not apply.
    """
    name = str(break_.get("name", ""))
    base, inner = name, ""
    m = re.match(r"^(.*?)\s*\((.*?)\)\s*$", name)  # "Kelp Beds (Esperance)" -> core + locality
    if m:
        base, inner = m.group(1).strip(), m.group(2).strip()

    # Query variants: parenthetical locality first, then the raw name, then
    # any parts of a slashed name ("Agnes Water / 1770" -> "Agnes Water").
    cores = [p.strip() for p in name.split("/") if p.strip()]
    cores.append(base)

    box = STATE_BOXES.get(state)
    d_old = _haversine_km(current, anchor) if (anchor and current) else None

    physical: list[tuple[float, float, float, str]] = []  # (score, lat, lng, dn)
    places: list[tuple[float, float, float, str]] = []
    seen: set[tuple[float, float]] = set()
    for query in dict.fromkeys(
        ([f"{base}, {inner}, {state}, Australia"] if inner else [])
        + [f"{c}, {state}, Australia" for c in dict.fromkeys(cores)]
        + [f"{base}, Australia"]
    ):
        try:
            hits = nominatim_search(query)
        except Exception as e:  # noqa: BLE001
            print(f"    ! Nominatim error for {query!r}: {e}")
            continue
        core = base if inner else cores[0]
        for cand in hits:
            if _norm(core) not in _norm(cand.get("display_name", "")):
                continue
            try:
                lat, lng = float(cand["lat"]), float(cand["lon"])
            except (KeyError, ValueError):
                continue
            if box and not _in_box(lat, lng, box):
                continue  # wrong corner of the state — never accept
            if (round(lat, 3), round(lng, 3)) in seen:
                continue
            kind = _candidate_kind(cand)
            if kind is None:
                continue
            seen.add((round(lat, 3), round(lng, 3)))
            entry = (_candidate_score(cand, anchor), lat, lng, cand.get("display_name", ""))
            (physical if kind == "physical" else places).append(entry)
        if physical:
            break  # a physical match is the best we will get

    # Cluster-distance gate (G2): if the existing point sits clearly closer
    # to the trusted region cluster than the OSM candidate, trust the cluster.
    def veto(point: tuple[float, float]) -> bool:
        if hard_fail or anchor is None or d_old is None or current is None:
            return False
        return d_old + 20.0 <= _haversine_km(point, anchor)

    if physical:
        physical.sort(key=lambda e: -e[0])  # best score first (type + anchor proximity)
        best = physical[0]
        if veto((best[1], best[2])):
            print("  -> candidate farther from region cluster than existing point")
            return None
        return (best[1], best[2], best[3])
    if len(places) == 1 and not veto((places[0][1], places[0][2])):
        return (places[0][1], places[0][2], places[0][3])
    if len(places) > 1 and d_old is not None and anchor is not None:
        # Several settlement hits: accept only if the existing point is the outlier.
        supported = [p for p in places if _haversine_km((p[1], p[2]), anchor) + 20.0 <= d_old]
        if supported:
            supported.sort(key=lambda p: _haversine_km((p[1], p[2]), anchor))
            if not veto((supported[0][1], supported[0][2])):
                return (supported[0][1], supported[0][2], supported[0][3])
    return None


def build_coord_prompt(break_: dict, current) -> str:
    cur = (
        f"The coordinates currently on file are lat {current[0]}, lng {current[1]} — "
        f"they are suspected to be wrong, so re-estimate from your real-world knowledge "
        f"of the spot rather than trusting them."
        if current
        else "The break currently has no usable coordinates on file."
    )
    return (
        "You are a surf-break geocoding assistant. You are given one Australian surf break. "
        "Return the real-world geographic coordinates of the break's primary takeoff zone "
        "(the actual point on the coast, not the nearest town centre) as JSON ONLY — "
        "no markdown fences, no commentary — in exactly this shape:\n"
        '{"lat": <decimal degrees, south is negative>, "lng": <decimal degrees, east is positive>}\n\n'
        f"Break: {break_.get('name')} — state: {break_.get('state')}, region: {break_.get('region')}\n"
        f"{cur}\n"
        f"Known description: {str(break_.get('description', ''))[:300]}"
    )


def fetch_corrected_coords(client: InferenceClient, break_: dict, current) -> tuple[float, float] | None:
    """One chat-completion call (with retries) asking for lat/lng only."""
    prompt = build_coord_prompt(break_, current)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            completion = client.chat.completions.create(
                model=MODEL_ID,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.0,
            )
            data = extract_json(completion.choices[0].message.content or "")
            lat, lng = float(data["lat"]), float(data["lng"])
            if math.isfinite(lat) and math.isfinite(lng):
                return lat, lng
        except Exception as e:  # noqa: BLE001
            print(f"  ! Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)
    return None


def fix_flagged(
    client: InferenceClient | None,
    breaks: list[dict],
    flagged: list[dict],
    max_fixes: int,
    source: str = "osm",
) -> None:
    """Replace coordinates on flagged breaks using a ground-truth source
    (OSM by default, LLM fallback for spots OSM doesn't know); save after
    each accepted fix."""
    fixed, kept = [], []
    backup = ENRICHED_FILE.with_name(f"{ENRICHED_FILE.stem}-backup-{datetime.now():%Y%m%d-%H%M%S}{ENRICHED_FILE.suffix}")
    backup_written = False

    # Anchor per (state, region): median of the unflagged breaks in the cluster.
    flagged_ids = {id(item["break"]) for item in flagged}
    clusters: dict[tuple, list[tuple[float, float]]] = defaultdict(list)
    for b in breaks:
        if id(b) in flagged_ids:
            continue
        p = _coords(b)
        if p:
            clusters[(b.get("state", ""), b.get("region", ""))].append(p)
    anchors = {
        k: (sorted(p[0] for p in pts)[len(pts) // 2], sorted(p[1] for p in pts)[len(pts) // 2])
        for k, pts in clusters.items()
    }

    for item in flagged:
        if len(fixed) + len(kept) >= max_fixes:
            print(f"Reached --max-fixes {max_fixes}, stopping.")
            break
        b = item["break"]
        label = f"{b.get('name')} ({b.get('state')} / {b.get('region')})"
        print(f"Fixing: {label} — flagged: {', '.join(item['reasons'])}")

        anchor = anchors.get((b.get("state", ""), b.get("region", "")))
        new, note = None, ""
        if source in ("osm", "both"):
            match = osm_match(b, b.get("state", ""), anchor)
            if match:
                new, note = (match[0], match[1]), match[2]
            else:
                print("  -> not found in OpenStreetMap")
        if new is None and source in ("llm", "both") and client is not None:
            llm = fetch_corrected_coords(client, b, item["coords"])
            if llm is not None:
                new, note = llm, "LLM estimate"
        if new is None:
            kept.append(label)
            print("  -> kept old coords (no ground-truth match found)")
            continue

        # Validate the proposal against the deterministic checks before accepting.
        others = [
            p
            for p in (_coords(o) for o in breaks if o is not b)
            if p is not None
        ]
        problems = check_point(new[0], new[1], b.get("state", ""), others)
        problems = [r for r in problems if r != "region_outlier"]  # outlier vs old cluster is expected
        if "duplicate" in item["reasons"]:  # old point was already a duplicate;
            problems = [r for r in problems if r != "duplicate"]  # adjacent spots may share a point
        if problems:
            kept.append(label)
            print(f"  -> kept old coords (new point fails: {', '.join(problems)})")
            continue

        if not backup_written:
            ENRICHED_FILE.replace(backup)
            backup_written = True
            print(f"Backup written to {backup}")
        b["location"]["coordinates"]["lat"] = round(new[0], 6)
        b["location"]["coordinates"]["lng"] = round(new[1], 6)
        fixed.append(label)
        print(f"  -> set to lat {new[0]:.4f}, lng {new[1]:.4f}  [{note}]")
        ENRICHED_FILE.write_text(json.dumps(breaks, indent=2))

    print(f"\nFixed {len(fixed)} break(s), kept old coords on {len(kept)}.")
    for label in kept:
        print(f"  - unresolved: {label}")


# ---------------------------------------------------------------- main

def main() -> None:
    args = [a for a in sys.argv[1:]]
    do_fix = "--fix" in args
    fix_all = "--all" in args
    source = "osm"
    if "--source" in args:
        source = args[args.index("--source") + 1]
        if source not in ("osm", "llm", "both"):
            raise SystemExit("--source must be osm, llm, or both")
    max_fixes = float("inf")
    if "--max-fixes" in args:
        max_fixes = int(args[args.index("--max-fixes") + 1])

    breaks = json.loads(ENRICHED_FILE.read_text())
    if not isinstance(breaks, list):
        raise SystemExit(f"{ENRICHED_FILE} is not a JSON list")
    print(f"Loaded {len(breaks)} breaks from {ENRICHED_FILE}")

    flagged = check_all(breaks)
    if not flagged:
        print("All coordinates passed every check. Nothing to do.")
        return

    print(f"\n{len(flagged)} flagged:\n")
    for item in flagged:
        b = item["break"]
        c = item["coords"]
        coords_str = f"lat {c[0]}, lng {c[1]}" if c else "missing/invalid"
        print(f"  [{', '.join(item['reasons'])}] {b.get('name')} ({b.get('state')} / {b.get('region')}) — {coords_str}")

    if not do_fix:
        print("\nRun with --fix to correct these against OpenStreetMap.")
        return

    targets = flagged if fix_all else [
        f for f in flagged if "invalid" in f["reasons"]
        or "out_of_australia" in f["reasons"]
        or "wrong_state" in f["reasons"]
        or "duplicate" in f["reasons"]
    ]
    skipped = len(flagged) - len(targets)
    if skipped > 0:
        print(f"\n--fix targets the {len(targets)} hard failures; {skipped} region outlier(s) "
              "skipped (use --all to include them).")

    client = None
    if source in ("llm", "both"):
        if not os.environ.get("HF_TOKEN"):
            raise SystemExit("HF_TOKEN is not set — required for --source llm/both.")
        client = InferenceClient(provider=PROVIDER, api_key=os.environ["HF_TOKEN"])

    fix_flagged(client, breaks, targets, max_fixes, source=source)

    # Re-run the checks on the in-memory list to show the final state.
    remaining = check_all(breaks)
    print(f"{len(remaining)} break(s) still flagged after fix attempt.")


if __name__ == "__main__":
    main()
