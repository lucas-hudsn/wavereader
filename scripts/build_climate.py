#!/usr/bin/env python3
"""Build per-break wave climatology from the Open-Meteo marine API.

Pulls ``https://marine-api.open-meteo.com/v1/marine`` with an explicit
historical ``start_date``/``end_date`` range (default model blend), daily
``swell_wave_height_max, swell_wave_direction_dominant,
swell_wave_period_max`` for the last 5 full calendar years, for every
break in ``data/australia-surf-breaks-enriched.json`` (~238 calls, 1 per
break).

DEVIATION from plan: the plan named ``/v1/archive`` on the marine host,
but that endpoint does not exist there (HTTP 404; archive-api.open-meteo.com
has no swell partitions either). ``/v1/marine`` accepts historical date
ranges directly. One caveat: swell partitions are only served from ~2022
onwards (2021 days come back null); the pipeline skips nulls, so profiles
cover ~4 of the 5 years for swell fields. ERA5-Ocean (``models=era5_ocean``)
goes back further but never carries swell partitions, so it is not used.

Polite (~1 req/s, configurable), resumable (skips slugs whose output
file already exists unless ``--overwrite``), robust to archive
misses/nulls. Writes ``data/climate/<id-slug>.json`` plus one
``data/climate/index.json`` manifest.

Polite (~1 req/s, configurable), resumable (skips slugs whose output
file already exists unless ``--overwrite``), robust to archive
misses/nulls. Writes ``data/climate/<id-slug>.json`` plus one
``data/climate/index.json`` manifest.

Usage:
    uv run python scripts/build_climate.py --help
    uv run python scripts/build_climate.py --limit 3
    uv run python scripts/build_climate.py --overwrite --limit 10
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import time
from pathlib import Path

import httpx

# Bootstrap: repo root on sys.path so `wavereader.climate` imports without
# requiring Worker A's `wavereader/__init__.py` (absent on v2-climate branch).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ---------------------------------------------------------------------------
# STUB (merge rewire): copied from app/forecasts.py::_seaward_offset.
# Worker A (branch v2-core) ports the canonical version to
# wavereader/openmeteo.py. At merge, replace this block with:
#   try:
#       from wavereader.openmeteo import _seaward_offset
#   except ImportError:
#       <keep this local copy as fallback>
# and delete this comment.
# ---------------------------------------------------------------------------
_SEAWARD_OFFSET_DEG = 0.15


def _seaward_offset(lat: float, lon: float) -> tuple[float, float]:  # STUB
    """Offset spot coords toward open ocean so Open-Meteo hits marine grid."""
    if lat <= -39.5:  # Tasmania: open ocean to the south
        dlat, dlon = -_SEAWARD_OFFSET_DEG, 0.0
    elif lon >= 147:  # east coast (QLD/NSW)
        dlat, dlon = 0.0, _SEAWARD_OFFSET_DEG
    elif lon <= 125:  # west coast (WA)
        dlat, dlon = 0.0, -_SEAWARD_OFFSET_DEG
    else:  # south coast (SA/VIC)
        dlat, dlon = -_SEAWARD_OFFSET_DEG, 0.0
    return dlat, dlon


try:
    # Canonical import once Worker A lands (kept as try/except so this
    # script works on the v2-climate branch where openmeteo.py is absent).
    from wavereader.openmeteo import _seaward_offset as _canonical_offset  # type: ignore

    _seaward_offset = _canonical_offset  # noqa: F811  (rewire at merge)
except ImportError:  # pragma: no cover - expected on v2-climate branch
    pass
# --- end STUB ---

from wavereader.climate import build_profile, filter_existing_slugs, slugify

ARCHIVE_URL = "https://marine-api.open-meteo.com/v1/marine"  # historical via start/end_date
DAILY_VARS = (
    "swell_wave_height_max,swell_wave_direction_dominant,swell_wave_period_max"
)


def last_five_full_years(
    today: _dt.date | None = None,
) -> tuple[str, str]:
    """Return (start, end) ISO dates for the last 5 full calendar years."""
    today = today or _dt.date.today()
    end_year = today.year - 1
    start_year = end_year - 4
    return f"{start_year}-01-01", f"{end_year}-12-31"


def load_breaks(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    recs = raw if isinstance(raw, list) else list(raw.values())
    return [r for r in recs if isinstance(r, dict) and not r.get("error")]


def break_coords(rec: dict) -> tuple[float, float] | None:
    try:
        lat = float(rec["location"]["coordinates"]["lat"])
        lon = float(rec["location"]["coordinates"]["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    return lat, lon


def fetch_archive(
    client: httpx.Client,
    lat: float,
    lon: float,
    start: str,
    end: str,
    timeout: float = 60.0,
) -> dict:
    params = {
        "latitude": round(lat, 2),
        "longitude": round(lon, 2),
        "start_date": start,
        "end_date": end,
        "daily": DAILY_VARS,
        "timezone": "UTC",
    }
    resp = client.get(ARCHIVE_URL, params=params, timeout=timeout)
    if resp.status_code == 429:  # polite backoff on rate limit, then one retry
        retry_after = int(resp.headers.get("retry-after", "60") or "60")
        time.sleep(min(max(retry_after, 30), 120))
        resp = client.get(ARCHIVE_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if "daily" not in payload:
        raise ValueError(f"archive response missing 'daily': keys={list(payload)}")
    return payload["daily"]


def build_one(
    client: httpx.Client,
    rec: dict,
    start: str,
    end: str,
    timeout: float,
) -> tuple[str, dict]:
    """Fetch archive + assemble profile for one break. Returns (slug, profile)."""
    break_id = str(rec.get("id") or rec.get("name", "break"))
    slug = slugify(break_id)
    coords = break_coords(rec)
    if coords is None:
        raise ValueError(f"no coordinates for {break_id!r}")
    lat, lon = coords
    dlat, dlon = _seaward_offset(lat, lon)
    qlat, qlon = round(lat + dlat, 2), round(lon + dlon, 2)
    daily = fetch_archive(client, qlat, qlon, start, end, timeout)
    dates = daily.get("time", []) or []
    heights = daily.get("swell_wave_height_max", []) or []
    directions = daily.get("swell_wave_direction_dominant", []) or []
    periods = daily.get("swell_wave_period_max", []) or []
    ideal = rec.get("idealSwell", {}) or {}
    size = ideal.get("sizeRangeFt", {}) or {}
    try:
        wmin = float(size.get("min")) if size.get("min") is not None else None
    except (TypeError, ValueError):
        wmin = None
    try:
        wmax = float(size.get("max")) if size.get("max") is not None else None
    except (TypeError, ValueError):
        wmax = None
    profile = build_profile(
        slug=slug,
        break_id=break_id,
        name=str(rec.get("name", break_id)),
        latitude=qlat,
        longitude=qlon,
        start=start,
        end=end,
        dates=list(dates),
        heights_m=list(heights),
        directions_deg=list(directions),
        periods_s=list(periods),
        window_min_ft=wmin,
        window_max_ft=wmax,
    )
    return slug, profile


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--breaks", default="data/australia-surf-breaks-enriched.json")
    p.add_argument("--out-dir", default="data/climate")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--delay", type=float, default=1.0, help="seconds between calls")
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--start", default=None, help="override period start YYYY-MM-DD")
    p.add_argument("--end", default=None, help="override period end YYYY-MM-DD")
    p.add_argument("--slug", action="append", default=None,
                   help="only build these slugs (repeatable)")
    p.add_argument("--reindex", action="store_true",
                   help="offline: rebuild index.json from files on disk, no API calls")
    return p.parse_args(argv)


def embed_catalogue(breaks_path: Path, out_dir: Path) -> int:
    """Copy built profiles into the catalogue's embedded ``climate`` keys.

    Readers (``wavereader.climate.break_climate``) prefer the embedded
    copy, so the catalogue must track every rebuild. Keyed on the same
    ``slugify(id or name)`` derivation the per-slug files use. Writes a
    timestamped backup before the first change (mirrors check_coords /
    check_coast). Returns the number of records updated.
    """
    data = json.loads(breaks_path.read_text(encoding="utf-8"))
    updated = 0
    backup: Path | None = None
    for rec in data:
        if not isinstance(rec, dict) or rec.get("error") is not None:
            continue
        slug = slugify(str(rec.get("id") or rec.get("name", "break")))
        path = out_dir / f"{slug}.json"
        if not path.exists():
            continue
        prof = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("climate") == prof:
            continue
        if backup is None:
            backup = breaks_path.with_name(
                f"{breaks_path.stem}-backup-{_dt.datetime.now():%Y%m%d-%H%M%S}{breaks_path.suffix}"
            )
            breaks_path.replace(backup)
        rec["climate"] = prof
        updated += 1
    if updated:
        breaks_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"embedded {updated} profiles into {breaks_path.name}")
    return updated


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    breaks_path = (repo / args.breaks) if not Path(args.breaks).is_absolute() else Path(args.breaks)
    out_dir = (repo / args.out_dir) if not Path(args.out_dir).is_absolute() else Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.reindex:  # offline manifest rebuild (e.g. after a rate-limited run)
        entries: dict[str, dict] = {}
        for path in sorted(out_dir.glob("*.json")):
            if path.name == "index.json":
                continue
            try:
                prof = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            entries[prof.get("slug", path.stem)] = {
                "slug": prof.get("slug", path.stem),
                "id": prof.get("break_id"),
                "name": prof.get("name"),
                "n_days": prof.get("n_days"),
                "period": prof.get("period"),
            }
        default_start, default_end = last_five_full_years()
        manifest = {
            "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "period": {
                "start": args.start or default_start,
                "end": args.end or default_end,
            },
            "count": len(entries),
            "breaks": [entries[k] for k in sorted(entries)],
            "errors": [],
        }
        (out_dir / "index.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        print(f"reindexed {len(entries)} profiles")
        return 0

    default_start, default_end = last_five_full_years()
    start, end = args.start or default_start, args.end or default_end

    recs = load_breaks(breaks_path)
    # Dedupe slugs deterministically (collision -> suffix -2, -3, ...).
    seen: dict[str, int] = {}
    slug_of: list[tuple[str, dict]] = []
    for rec in recs:
        base = slugify(str(rec.get("id") or rec.get("name", "break")))
        n = seen.get(base, 0) + 1
        seen[base] = n
        slug_of.append((base if n == 1 else f"{base}-{n}", rec))
    if args.slug:
        wanted = set(args.slug)
        slug_of = [(s, r) for s, r in slug_of if s in wanted]
    if args.limit is not None:
        slug_of = slug_of[: args.limit]

    todo = filter_existing_slugs([s for s, _ in slug_of], out_dir, args.overwrite)
    todo_set = set(todo)
    print(f"period {start}..{end}, breaks {len(slug_of)}, to-fetch {len(todo)}")

    manifest_path = out_dir / "index.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries: dict[str, dict] = {e["slug"]: e for e in manifest.get("breaks", [])}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        entries = {}

    errors: list[dict] = []
    done = 0
    with httpx.Client(headers={"User-Agent": "wavereader-climate/2.0"}) as client:
        for i, (slug, rec) in enumerate(slug_of):
            if slug not in todo_set:
                continue
            try:
                _, profile = build_one(client, rec, start, end, args.timeout)
            except Exception as exc:  # robust: record + continue
                errors.append({"slug": slug, "error": f"{type(exc).__name__}: {exc}"})
                print(f"[{i + 1}/{len(slug_of)}] {slug}: ERROR {exc}")
            else:
                (out_dir / f"{slug}.json").write_text(
                    json.dumps(profile, indent=1), encoding="utf-8"
                )
                entries[slug] = {
                    "slug": slug,
                    "id": profile["break_id"],
                    "name": profile["name"],
                    "n_days": profile["n_days"],
                    "period": profile["period"],
                }
                done += 1
                print(f"[{i + 1}/{len(slug_of)}] {slug}: ok ({profile['n_days']}d)")
            # Polite rate limit (skip sleep after the final call).
            if args.delay > 0 and i < len(slug_of) - 1:
                time.sleep(args.delay)

    manifest = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "period": {"start": start, "end": end},
        "count": len(entries),
        "breaks": [entries[k] for k in sorted(entries)],
        "errors": errors,
    }
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"wrote {done} new profiles, manifest count={len(entries)}, errors={len(errors)}")
    embed_catalogue(breaks_path, out_dir)
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
