"""Open-Meteo Marine + weather forecast client.

Two endpoints, merged on ``time``:

* ``marine-api.open-meteo.com`` — hourly ``wave_height`` (m),
  ``wave_period`` (s), ``wave_direction`` (deg), ``wind_wave_height`` (m),
  ``swell_wave_height`` (m). Verified 2026-08-30 at Snapper Rocks: 48
  hourly entries, no nulls, ~1.3 m @ ~6 s from ~SE. The marine endpoint
  does NOT serve wind fields.
* ``api.open-meteo.com`` — hourly ``wind_speed_10m`` (km/h; convert to
  knots for scoring) and ``wind_direction_10m`` (deg).

Grid points snap ~10 km offshore of a spot's coords (Snapper Rocks
-28.173,153.556 resolved to -28.04,153.63). Fetch slightly seaward and
keep the offset consistent across all spots.

Cache every response to disk: the demo must survive API flakiness and
rate limits. Horizon: hourly, 7 days.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

MARINE_HOURLY_FIELDS = (
    "wave_height",
    "wave_period",
    "wave_direction",
    "wind_wave_height",
    "swell_wave_height",
)
WEATHER_HOURLY_FIELDS = ("wind_speed_10m", "wind_direction_10m")

_SNAP_OFFSET = (-0.133, 0.074)

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "forecasts"


def _round_coords(lat: float, lon: float) -> tuple[float, float]:
    return round(lat + _SNAP_OFFSET[0], 2), round(lon + _SNAP_OFFSET[1], 2)


def _cache_key(lat: float, lon: float, days: int) -> str:
    return f"{lat:.2f}_{lon:.2f}_{days}"


def _cache_path(lat: float, lon: float, days: int) -> Path:
    return CACHE_DIR / f"{_cache_key(lat, lon, days)}.json"


def _load_cache(lat: float, lon: float, days: int) -> dict | None:
    p = _cache_path(lat, lon, days)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _save_cache(lat: float, lon: float, days: int, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(lat, lon, days).write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def _build_normalized(marine: dict, weather: dict) -> dict:
    """Merge marine + weather hourly on ``time`` into a clean frame."""
    m = marine["hourly"]
    w = weather["hourly"]
    marine_times = m["time"]

    weather_index: dict[str, dict[str, float]] = {}
    for i, t in enumerate(w["time"]):
        entry: dict[str, float] = {"time": t}
        for field in WEATHER_HOURLY_FIELDS:
            if field in w and i < len(w[field]):
                entry[field] = w[field][i]
        weather_index[t] = entry

    frames: list[dict] = []
    for i, t in enumerate(marine_times):
        row: dict[str, float | str] = {"time": t}
        for field in MARINE_HOURLY_FIELDS:
            if field in m and i < len(m[field]):
                row[field] = m[field][i]
        wr = weather_index.get(t)
        if wr:
            for field in WEATHER_HOURLY_FIELDS:
                if field in wr:
                    row[field] = wr[field]
        frames.append(row)

    return {"hourly": frames}


def get_forecast(lat: float, lon: float, days: int = 7) -> dict:
    """Fetch marine + weather hourly data for a coordinate, merged on time.

    Returns a normalised frame: ``{"hourly": [{"time": ..., "wave_height": ...,
    "wind_speed_10m": ..., ...}, ...]}``.  Disk-cached by rounded coords + days.
    """
    rlat, rlon = _round_coords(lat, lon)
    cached = _load_cache(rlat, rlon, days)
    if cached is not None:
        return cached

    params: dict[str, str | int | float] = {
        "latitude": rlat,
        "longitude": rlon,
        "forecast_days": days,
    }

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        resp_m = client.get(MARINE_URL, params={**params, "hourly": ",".join(MARINE_HOURLY_FIELDS)})
        resp_m.raise_for_status()
        marine = resp_m.json()
        resp_w = client.get(WEATHER_URL, params={**params, "hourly": ",".join(WEATHER_HOURLY_FIELDS)})
        resp_w.raise_for_status()
        weather = resp_w.json()

    merged = _build_normalized(marine, weather)
    _save_cache(rlat, rlon, days, merged)
    return merged


if __name__ == "__main__":
    result = get_forecast(-28.173, 153.556, days=2)
    print(f"Fetched {len(result['hourly'])} hourly rows")
    if result["hourly"]:
        print("First:", result["hourly"][0])
        print("Last:", result["hourly"][-1])