#!/usr/bin/env python
"""Warm the wave~reader caches so the demo spins up hot.

Pre-fetches (through the real v2 core, disk-cached):
  * Open-Meteo marine+wind 7-day forecasts   -> .cache/forecasts/
  * GEBCO 2020 seafloor grids (10x10)        -> .cache/seafloor/

Usage:
  uv run python scripts/warm_caches.py                # featured demo breaks
  uv run python scripts/warm_caches.py --all          # whole catalogue (slow)
  uv run python scripts/warm_caches.py --state TAS    # one state

Open-Meteo is free/no key; GEBCO via OpenTopoData is rate-limited
(~1 call/s), so the seafloor loop dominates: ~1.3 s per cold break.
"""

from __future__ import annotations

import argparse
import sys
import time

FEATURED = [
    "Bells Beach", "Snapper Rocks", "Bondi Beach", "Shipstern Bluff",
    "Kirra", "Margaret River", "Crescent Head", "Clifton Beach",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="warm wave~reader caches")
    ap.add_argument("--all", action="store_true", help="warm every break (slow)")
    ap.add_argument("--state", default=None, help="warm one state, e.g. TAS")
    ap.add_argument("--skip-seafloor", action="store_true", help="forecast only")
    args = ap.parse_args()

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

    from ui import _compat as C

    records = C.list_breaks()
    if args.all:
        picks = records
    elif args.state:
        want = args.state.strip().lower()
        picks = [r for r in records if str(r.get("state", "")).lower() == want]
    else:
        picks = [b for b in (C.find_break(records, n) for n in FEATURED) if b]
    if not picks:
        print("no breaks matched")
        return 1
    print(f"warming {len(picks)} break(s) — forecast{' + seafloor' if not args.skip_seafloor else ''}")

    t_all = time.perf_counter()
    ok = fail = 0
    for i, b in enumerate(picks, 1):
        name = b.get("name", "?")
        t0 = time.perf_counter()
        try:
            C.get_scored_week(b, skill="intermediate", days=7)
            f_ms = (time.perf_counter() - t0) * 1000
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}/{len(picks)}] ❌ {name}: forecast failed: {e}")
            fail += 1
            continue
        if args.skip_seafloor:
            print(f"  [{i}/{len(picks)}] 📡 {name} — {f_ms:.0f} ms")
            ok += 1
            continue
        t1 = time.perf_counter()
        try:
            sea = C.get_seafloor(b)
            s_ms = (time.perf_counter() - t1) * 1000
            pts = len((sea.get("grid") or {}).get("elev") or [])
            print(f"  [{i}/{len(picks)}] 📡 {name} — {f_ms:.0f} ms · "
                  f"🌍 {pts} pts — {s_ms / 1000:.1f} s")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}/{len(picks)}] ⚠️ {name} — forecast ok, seafloor failed: {e}")
            ok += 1
    print(f"done: {ok} ok, {fail} failed in {time.perf_counter() - t_all:.1f} s")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
