"""
check_coast.py — verify (and optionally fix) that every break coordinate
sits on the coastline: ≈0 m elevation on the GEBCO 2020 grid.

Why: the seafloor world model (``wavereader.seafloor``) samples a 1.2 km
box centred on the break coordinates. When a break's point sits inland or
well offshore, the depth map / 3D view is mis-anchored (all land, or all
water, with the takeoff marker nowhere near the shore). ``check_coords.py``
keeps points in the right state/region but says nothing about sea level;
this script closes that gap.

Phase 1 AUDIT (~3 batched API calls) — fetch the GEBCO 2020 elevation of
every break coordinate via OpenTopoData (same free source as
``wavereader.seafloor``) and classify:

    waterline   |elev| <= 3 m            (target state)
    inland      elev > 3 m
    offshore    elev < -3 m

Phase 2 FIX (--fix) — for each non-waterline break, find the nearest 0 m
crossing on the GEBCO grid and move the break there:

    1. one 10x10 grid (1.2 km box, one API call) around the break; take
       the nearest cell on the opposite side of 0 (water for inland
       breaks, land for offshore ones); expand the box (3, 5, 9, 14,
       18 km) when no opposite-side cell exists;
    2. batch-sampled bisection along the break→cell segment (the anchor
       cell's own elevation closes the t=1.0 end), linearly interpolated
       to the 0 m crossing, then refined inside the bracket;
    3. deterministic validation before accepting: new elevation within
       tolerance, move distance <= 18 km, still inside the state box.
       Two breaks snapping near each other is normal (adjacent spots on
       one beach): the second point slides shore-parallel to keep both
       coordinates distinct instead of being rejected.

A timestamped backup is written before the first change; the file is
saved after every accepted fix. OpenTopoData free tier is ~1 call/s, so a
full audit+fix run takes ~5 minutes for 238 breaks.

Usage:
    uv run python scripts/check_coast.py             # audit only
    uv run python scripts/check_coast.py --fix       # snap non-coastal breaks to the shoreline
    uv run python scripts/check_coast.py --fix --dedupe
    uv run python scripts/check_coast.py --dedupe    # spread breaks sharing a shoreline point
    uv run python scripts/check_coast.py --fix --max-fixes 10
"""

from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

# Bootstrap: repo root + scripts/ on sys.path so `wavereader.*` and the
# sibling check_coords helpers resolve when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_coords import _haversine_km, check_point  # noqa: E402

from wavereader.breaks import DATA_PATH as ENRICHED_FILE  # noqa: E402

OPENTOPO_URL = "https://api.opentopodata.org/v1/gebco2020"

WATERLINE_TOL_M = 3.0   # |elev| <= this counts as "on the coast"
ACCEPT_TOL_M = 5.0      # largest elevation an accepted snap may carry
MAX_MOVE_KM = 18.0      # never drag a break farther than the search radius
GRID_N = 10             # 10x10 = 100 pts -> exactly one API call per break
RADII_KM = (1.2, 3.0, 5.0, 9.0, 14.0, 18.0)
KM_PER_DEG_LAT = 111.0
PACING_S = 1.05         # OpenTopoData free tier: 1 call/sec

BISECT_TS = (0.15, 0.3, 0.45, 0.6, 0.75, 0.9)

_last_call = 0.0


def _pace() -> None:
    global _last_call
    wait = PACING_S - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()


def fetch_elevations(points: list[tuple[float, float]]) -> list[float | None]:
    """Elevation (m, GEBCO 2020) for each (lat, lng); None on per-point miss.

    Batches 100 locations per call (OpenTopoData's max), paced to 1 call/s,
    with short retries on transient failures.
    """
    out: list[float | None] = []
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for i in range(0, len(points), 100):
            chunk = points[i : i + 100]
            locs = [f"{la:.5f},{lo:.5f}" for la, lo in chunk]
            done = False
            for attempt in (1, 2, 3):
                _pace()
                try:
                    resp = client.get(OPENTOPO_URL, params={"locations": "|".join(locs)})
                    resp.raise_for_status()
                    body = resp.json()
                    if body.get("status") != "OK":
                        raise ValueError(f"OpenTopoData status {body.get('status')}")
                    out.extend(r.get("elevation") for r in body.get("results", []))
                    done = True
                    break
                except (httpx.HTTPError, ValueError) as e:  # noqa: BLE001
                    if attempt == 3:
                        print(f"  ! elevation fetch failed for {len(chunk)} pts: {e}")
                    else:
                        time.sleep(2 * attempt)
            if not done:
                out.extend([None] * len(chunk))
    return out


def _coords(break_: dict) -> tuple[float, float] | None:
    try:
        lat = float(break_["location"]["coordinates"]["lat"])
        lng = float(break_["location"]["coordinates"]["lng"])
        if math.isfinite(lat) and math.isfinite(lng):
            return lat, lng
    except (KeyError, TypeError, ValueError):
        pass
    return None


# ---------------------------------------------------------------- audit

def audit(breaks: list[dict]) -> list[dict]:
    """Classify every break by the GEBCO elevation at its coordinates."""
    pts = [_coords(b) for b in breaks]
    elevs = fetch_elevations([p for p in pts if p is not None])
    rows, i = [], 0
    for b, p in zip(breaks, pts):
        if p is None:
            rows.append({"break": b, "coords": None, "elev_m": None, "cls": "invalid"})
            continue
        e = elevs[i]
        i += 1
        if e is None:
            cls = "unknown"
        elif abs(e) <= WATERLINE_TOL_M:
            cls = "waterline"
        else:
            cls = "inland" if e > 0 else "offshore"
        rows.append({"break": b, "coords": p, "elev_m": e, "cls": cls})
    return rows


def print_audit(rows: list[dict], header: str) -> None:
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["cls"]] = counts.get(r["cls"], 0) + 1
    print(f"\n{header}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


# ---------------------------------------------------------------- coastline search

def _offsets(lat: float, radius_km: float, n: int) -> tuple[list[float], list[float]]:
    """Lat/lng offsets for an n x n grid spanning ±radius_km (same geometry
    as ``wavereader.seafloor._deg_offsets``)."""
    dlat = radius_km / KM_PER_DEG_LAT
    dlon = radius_km / max(20.0, KM_PER_DEG_LAT * math.cos(math.radians(lat)))
    return (
        [((i / (n - 1)) * 2 - 1) * dlat for i in range(n)],
        [((j / (n - 1)) * 2 - 1) * dlon for j in range(n)],
    )


def find_opposite_cell(lat: float, lng: float, inland: bool) -> tuple[float, float, float | None] | None:
    """Nearest cell on the far side of 0 m, searching ever-wider boxes.

    Inland breaks look for the nearest water cell (elev < 0); offshore
    breaks for the nearest land cell (elev >= 0). One API call per radius.
    Returns ``(lat, lng, elev)`` — the elevation lets the bisection treat
    the anchor as a known t=1.0 sample.
    """
    for radius in RADII_KM:
        lats_o, lngs_o = _offsets(lat, radius, GRID_N)
        lats = [round(lat + d, 5) for d in lats_o]
        lngs = [round(lng + d, 5) for d in lngs_o]
        pts = [(la, lo) for la in lats for lo in lngs]
        elevs = fetch_elevations(pts)
        best, best_d, best_e = None, math.inf, None
        for (la, lo), e in zip(pts, elevs):
            if e is None:
                continue
            if (e < 0) if inland else (e >= 0):
                d = _haversine_km((lat, lng), (la, lo))
                if d < best_d:
                    best, best_d, best_e = (la, lo), d, e
        if best is not None:
            return (*best, best_e)
    return None


def _lerp(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _crossing_t(t0: float, e0: float, t1: float, e1: float) -> float:
    """t of the 0 m crossing on the segment (t0, e0)–(t1, e1)."""
    return t0 + (e0 - 0.0) / (e0 - e1) * (t1 - t0)


DUP_CLEAR_DEG = 0.006  # clears check_coords' 0.005-degree duplicate box


def _clears_dups(p: tuple[float, float], others: list[tuple[float, float]]) -> bool:
    return all(abs(p[0] - o[0]) >= DUP_CLEAR_DEG or abs(p[1] - o[1]) >= DUP_CLEAR_DEG
               for o in others)


def walk_along_shore(row: dict, new: tuple[float, float],
                     others: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Slide a snapped point shore-parallel until it clears the duplicate
    radius of every other break.

    Adjacent spots on one beach (Snapper Rocks / Greenmount / Duranbah)
    legitimately snap near each other; instead of rejecting the snap, the
    point moves along the shore — the perpendicular of the break→anchor
    segment — preferring the offset closest to the break's previous
    position. Returns a point, or None when every offset still collides.
    """
    ax, ay = row["anchor"]
    ux, uy = ax - row["coords"][0], ay - row["coords"][1]
    n = math.hypot(ux, uy) or 1.0
    px, py = uy / n, -ux / n
    cands = [
        (new[0] + sign * k * 0.002 * px, new[1] + sign * k * 0.002 * py)
        for k in (1, 2, 3, 4, 5) for sign in (1, -1)
    ]
    cands.sort(key=lambda c: _haversine_km(c, row["coords"]))
    for cand in cands:
        if _clears_dups(cand, others):
            return cand
    return None


def snap_rows(rows: list[dict]) -> None:
    """Compute the 0 m crossing for every non-waterline row in place.

    Fills ``row["new_coords"]`` (and ``row["new_elev"]`` where verified),
    or sets ``row["error"]`` and leaves the coords alone.
    """
    todo = [r for r in rows if r["cls"] in ("inland", "offshore") and r["coords"]]

    # 1. opposite-side anchor cell per break (one grid call each).
    print(f"\nFinding the nearest coastline cell for {len(todo)} break(s)…")
    unresolved: list[str] = []
    for i, row in enumerate(todo):
        lat, lng = row["coords"]
        opp = find_opposite_cell(lat, lng, row["cls"] == "inland")
        if opp is None:
            row["error"] = "no opposite-side cell within the search radii"
            unresolved.append(row["break"].get("name", "?"))
        else:
            row["anchor"], row["anchor_elev"] = (opp[0], opp[1]), opp[2]
        if (i + 1) % 25 == 0:
            print(f"  [{i + 1}/{len(todo)}] coastline cells located")
    if unresolved:
        print(f"  ! no coastline found near: {', '.join(unresolved)}")
    todo = [r for r in todo if "error" not in r]

    # 2. batch-sampled bisection: sample all segments together, then find
    #    each one's 0 m crossing between the sign-flipping samples.
    def sample(ts_for: dict[int, list[float]]) -> None:
        pts: list[tuple[float, float]] = []
        idx: list[tuple[int, float]] = []
        for i, ts in ts_for.items():
            row = todo[i]
            for t in ts:
                pts.append(_lerp(row["coords"], row["anchor"], t))
                idx.append((i, t))
        elevs = fetch_elevations(pts)
        for (i, t), e in zip(idx, elevs):
            todo[i].setdefault("samples", {})[t] = e

    sample({i: list(BISECT_TS) for i in range(len(todo))})
    for row in todo:
        s = row["samples"]
        # The path spans the whole segment: t=0 is the break's audited
        # elevation, t=1 the anchor cell's known elevation, 0.15..0.9 the
        # sampled points in between.
        path = sorted({0.0, 1.0, *s})
        elevs = [
            row["elev_m"] if t == 0.0 else (row.get("anchor_elev") if t == 1.0 else s.get(t))
            for t in path
        ]
        row["bracket"] = None
        for (t0, t1), (e0, e1) in zip(zip(path, path[1:]), zip(elevs, elevs[1:])):
            if e0 is None or e1 is None:
                continue
            # Same predicate find_opposite_cell used to pick the anchor —
            # shoreline cells quantized to exactly 0 m count as land.
            flip = (e0 >= 0 > e1) if row["cls"] == "inland" else (e0 < 0 <= e1)
            if flip:
                row["bracket"] = (t0, e0, t1, e1)
                break

    # 3. refine inside each bracket, then interpolate.
    brack = {i: r["bracket"] for i, r in enumerate(todo) if r["bracket"]}
    sample({i: [b[0] + f * (b[2] - b[0]) for f in (0.25, 0.5, 0.75)]
            for i, b in brack.items()})
    for row in todo:
        if row["bracket"] is None:
            row["error"] = "no 0 m crossing along the search segment"
            continue
        b = row["bracket"]
        # Elevation lookup across the whole segment: the endpoints (t=0 the
        # break itself, t=1 the anchor cell) were never sampled into
        # row["samples"], so they are folded in explicitly — a bracket that
        # ends at the anchor must stay resolvable here.
        elev_of = {0.0: row["elev_m"], 1.0: row.get("anchor_elev"), **row["samples"]}
        path = sorted(t for t in {b[0], b[2], *elev_of} if b[0] <= t <= b[2])
        pts_in = [(t, elev_of.get(t)) for t in path]
        cross = None
        for (t0, e0), (t1, e1) in zip(pts_in, pts_in[1:]):
            if e0 is None or e1 is None:
                continue
            flip = (e0 >= 0 > e1) if row["cls"] == "inland" else (e0 < 0 <= e1)
            if not flip:
                continue
            cross = _crossing_t(t0, e0, t1, e1)
            break
        if cross is None:
            row["error"] = "no 0 m crossing along the search segment"
            continue
        row["new_coords"] = _lerp(row["coords"], row["anchor"], cross)
    # Elevation of each snapped point gets verified by the caller.

    missed = [r["break"].get("name", "?") for r in todo if "error" in r]
    if missed:
        print(f"  ! no 0 m crossing found for {len(missed)}: {', '.join(missed)}")


# ---------------------------------------------------------------- fix

def fix(rows: list[dict], breaks: list[dict], max_fixes: int) -> None:
    todo = [r for r in rows if r.get("new_coords")]
    todo = todo[:max_fixes] if max_fixes < len(todo) else todo
    if not todo:
        print("\nNothing to fix (or nothing snappable).")
        return

    backup = ENRICHED_FILE.with_name(
        f"{ENRICHED_FILE.stem}-backup-{datetime.now():%Y%m%d-%H%M%S}{ENRICHED_FILE.suffix}"
    )
    backup_written = False
    fixed, kept = [], []

    # Verify the elevation of every snapped point in one batched pass.
    elevs = fetch_elevations([r["new_coords"] for r in todo])
    for row, e in zip(todo, elevs):
        row["new_elev"] = e

    for row in todo:
        b = row["break"]
        label = f"{b.get('name')} ({b.get('state')} / {b.get('region')})"
        old, new = row["coords"], row["new_coords"]
        e_new = row.get("new_elev")

        # The interpolated crossing can still verify a few metres off on
        # coarse GEBCO cells; if a sampled point inside the bracket measured
        # closer to 0 m, prefer it — its elevation is already known.
        if e_new is not None and abs(e_new) > WATERLINE_TOL_M and row.get("bracket"):
            b0, _, b2, _ = row["bracket"]
            in_bracket = [
                (t, e) for t, e in {**row["samples"], 1.0: row.get("anchor_elev")}.items()
                if e is not None and b0 <= t <= b2
            ]
            if in_bracket:
                t_best, e_best = min(in_bracket, key=lambda te: abs(te[1]))
                if abs(e_best) < abs(e_new):
                    new = _lerp(row["coords"], row["anchor"], t_best)
                    e_new = e_best

        others = [p for p in (_coords(o) for o in breaks if o is not b) if p is not None]
        reasons = check_point(new[0], new[1], b.get("state", ""), others)
        # A "duplicate" here means two breaks snapped within ~550 m of each
        # other — normal for adjacent spots on one beach. Slide the point
        # along the shoreline so both keep distinct coordinates; if the
        # slid point fails the elevation check, sharing a beach with a
        # neighbour still beats being off the coast.
        if "duplicate" in reasons:
            slid = walk_along_shore(row, new, others)
            if slid is not None:
                e_slid = fetch_elevations([slid])[0]
                if e_slid is not None and abs(e_slid) <= ACCEPT_TOL_M:
                    new, e_new = slid, e_slid
            reasons = [r for r in reasons if r != "duplicate"]

        move_km = _haversine_km(old, new)
        if e_new is None:
            reasons.append("elevation unverified")
        elif abs(e_new) > ACCEPT_TOL_M:
            reasons.append(f"new point still {e_new:+.1f} m")
        if move_km > MAX_MOVE_KM:
            reasons.append(f"move {move_km:.1f} km > {MAX_MOVE_KM} km cap")
        if reasons:
            kept.append(label)
            print(f"  - kept {label}: {'; '.join(reasons)}")
            continue

        if not backup_written:
            ENRICHED_FILE.replace(backup)
            backup_written = True
            print(f"Backup written to {backup}")
        b["location"]["coordinates"]["lat"] = round(new[0], 6)
        b["location"]["coordinates"]["lng"] = round(new[1], 6)
        fixed.append(label)
        note = f"{row['elev_m']:+.0f} m -> {e_new:+.1f} m" if e_new is not None else "elevation unverified"
        print(f"  + {label}: {move_km * 1000:.0f} m ashore ({note})")
        ENRICHED_FILE.write_text(json.dumps(breaks, indent=2))

    print(f"\nSnapped {len(fixed)} break(s) to the coastline, kept {len(kept)} on old coords.")


# ---------------------------------------------------------------- dedupe

def _shore_axis_probe_points(lat: float, lng: float) -> list[tuple[float, float]]:
    """N/S/E/W probes ~280 m out, used to find the local shore direction."""
    d = 0.0025
    dl = d / max(0.2, math.cos(math.radians(lat)))
    return [(lat + d, lng), (lat - d, lng), (lat, lng + dl), (lat, lng - dl)]


def _shore_axis_from_probes(
    lat: float, lng: float, entries: list[tuple[tuple[float, float], float | None]]
) -> tuple[float, float]:
    """Shore-parallel unit step (dlat, dlng): the water-most probe marks the
    seaward side, so the shore runs along the perpendicular axis."""
    known = [(e, p) for p, e in entries if e is not None]
    if not known:
        return (1.0, 0.0)
    _, (wlat, wlng) = min(known)
    north_south = abs(wlat - lat) > abs(wlng - lng)
    return (0.0, 1.0) if north_south else (1.0, 0.0)


def dedupe(breaks: list[dict]) -> None:
    """Spread breaks that snapped onto (nearly) the same shoreline point.

    Groups breaks within check_coords' duplicate box, then assigns each
    member an offset along the group's shore-parallel axis — the middle of
    the group stays put — so adjacent spots keep distinct coordinates
    while every point stays on the waterline. Each candidate is verified
    at |elev| <= WATERLINE_TOL; a failing candidate keeps its old point.
    """
    def coords(b: dict) -> tuple[float, float]:
        c = b["location"]["coordinates"]
        return (float(c["lat"]), float(c["lng"]))

    parent = list(range(len(breaks)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    pts = [coords(b) for b in breaks]
    for i in range(len(breaks)):
        for j in range(i + 1, len(breaks)):
            if abs(pts[i][0] - pts[j][0]) < 0.005 and abs(pts[i][1] - pts[j][1]) < 0.005:
                parent[find(i)] = find(j)

    groups: dict[int, list[int]] = {}
    for i in range(len(breaks)):
        groups.setdefault(find(i), []).append(i)
    groups = [m for m in groups.values() if len(m) > 1]
    if not groups:
        print("No colliding breaks — every point is distinct.")
        return
    for members in groups:
        print(f"  group: {', '.join(breaks[i]['name'] for i in members)}")

    # One shore axis per group, probed at the group's first point.
    probe_pts, probe_owner = [], []
    for gi, members in enumerate(groups):
        for p in _shore_axis_probe_points(*pts[members[0]]):
            probe_pts.append(p)
            probe_owner.append(gi)
    probe_elevs = fetch_elevations(probe_pts)
    by_group: dict[int, list[tuple[tuple[float, float], float | None]]] = {}
    for gi, p, e in zip(probe_owner, probe_pts, probe_elevs):
        by_group.setdefault(gi, []).append((p, e))
    axes = {gi: _shore_axis_from_probes(*pts[groups[gi][0]], entries) for gi, entries in by_group.items()}

    STEP = 0.004  # ~440 m between adjacent members of a group
    backup = ENRICHED_FILE.with_name(
        f"{ENRICHED_FILE.stem}-backup-{datetime.now():%Y%m%d-%H%M%S}{ENRICHED_FILE.suffix}"
    )
    backup_written = False
    moved = 0
    cands = []
    for gi, members in enumerate(groups):
        base = pts[members[0]]
        s = axes[gi]
        for pos, bi in enumerate(members):
            k = (pos - (len(members) - 1) / 2) * STEP
            cands.append((bi, base[0] + k * s[0], base[1] + k * s[1]))
    elevs = fetch_elevations([(la, lo) for _, la, lo in cands])
    for (bi, la, lo), e in zip(cands, elevs):
        b = breaks[bi]
        old = pts[bi]
        if (la, lo) == old or e is None or abs(e) > WATERLINE_TOL_M:
            continue
        if not backup_written:
            ENRICHED_FILE.replace(backup)
            backup_written = True
            print(f"Backup written to {backup}")
        b["location"]["coordinates"]["lat"] = round(la, 6)
        b["location"]["coordinates"]["lng"] = round(lo, 6)
        moved += 1
        print(f"  ~ {b['name']}: spread {_haversine_km(old, (la, lo)) * 1000:.0f} m along the shore (elev {e:+.1f} m)")
    print(f"Spread {moved} break(s) across {len(groups)} colliding group(s).")


def _shore_axis_probe_points(lat: float, lng: float) -> list[tuple[float, float]]:
    d = 0.0025
    dl = d / max(0.2, math.cos(math.radians(lat)))
    return [(lat + d, lng), (lat - d, lng), (lat, lng + dl), (lat, lng - dl)]


def _shore_axis_from_probes(lat, lng, entries) -> tuple[float, float]:
    known = [(e, p) for p, e in entries if e is not None]
    if not known:
        return (1.0, 0.0)
    _, (wlat, wlng) = min(known)
    north_south = abs(wlat - lat) > abs(wlng - lng)
    return (0.0, 1.0) if north_south else (1.0, 0.0)


# ---------------------------------------------------------------- main

def main() -> None:
    args = sys.argv[1:]
    do_fix = "--fix" in args
    do_dedupe = "--dedupe" in args
    max_fixes = int(args[args.index("--max-fixes") + 1]) if "--max-fixes" in args else 10**9

    breaks = json.loads(ENRICHED_FILE.read_text(encoding="utf-8"))
    if not isinstance(breaks, list):
        raise SystemExit(f"{ENRICHED_FILE} is not a JSON list")
    print(f"Loaded {len(breaks)} breaks from {ENRICHED_FILE}")

    if do_dedupe and not do_fix:
        dedupe(breaks)
        print_audit(audit(breaks), "Final audit")
        return

    rows = audit(breaks)
    print_audit(rows, "Audit (GEBCO 2020 elevation at each break coordinate)")
    if not do_fix:
        inland = [r for r in rows if r["cls"] == "inland"]
        offshore = [r for r in rows if r["cls"] == "offshore"]
        for tag, group in (("inland", inland), ("offshore", offshore)):
            for r in sorted(group, key=lambda r: -(r["elev_m"] or 0))[:10]:
                print(f"  [{tag:8s}] {r['elev_m']:+7.1f} m  {r['break'].get('name')}")
        print("\nRun with --fix to snap non-waterline breaks to the nearest 0 m crossing.")
        return

    snap_rows(rows)
    fix(rows, breaks, max_fixes)
    if do_dedupe:
        dedupe(breaks)

    final = audit(breaks)
    print_audit(final, "Final audit")
    for r in final:
        if r["cls"] != "waterline":
            b = r["break"]
            print(f"  ! still off-coast: {b.get('name')} ({b.get('state')}) at {r['elev_m']:+.1f} m")


if __name__ == "__main__":
    main()
