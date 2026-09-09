"""Open-Meteo Marine + weather forecast client (wavereader v2 core port).

Ported verbatim-first from ``app/forecasts.py``. v2 changes:

* marine fetch adds hourly ``swell_wave_direction`` and
  ``swell_wave_period`` (scoring v2 prefers ``swell_wave_*`` components
  over the generic ``wave_*`` aggregates when present);
* ``CACHE_VERSION`` bumped 2 → 3, so old-shape cache entries (without the
  new swell fields) are never served as fresh.

Two endpoints, merged on ``time``:

* ``marine-api.open-meteo.com`` — hourly ``wave_height`` (m),
  ``wave_period`` (s), ``wave_direction`` (deg), ``wind_wave_height`` (m),
  ``swell_wave_height`` (m), ``swell_wave_direction`` (deg),
  ``swell_wave_period`` (s), ``sea_surface_temperature`` (C, when served).
* ``api.open-meteo.com`` — hourly ``wind_speed_10m`` (km/h; convert to
  knots for scoring), ``wind_direction_10m`` (deg),
  ``wind_gusts_10m`` (km/h, when served), plus ``daily``
  ``sunrise``/``sunset`` (ISO local, ``timezone=auto``) used by the
  scoring v2 daylight filter.

Grid points snap ~10 km offshore of a spot's coords: fetch slightly
seaward of the spot (east-coast breaks shift east, west-coast breaks
shift west, south-coast breaks (SA/VIC/TAS) shift south).

Cache every response to disk. Fresh cache (within ``CACHE_TTL_SECONDS``)
is served without a network call; when the API fails, a stale cache
entry is served as a fallback rather than raising. Horizon: hourly,
7 days.
"""

from __future__ import annotations

import json
import os
import time
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
    "swell_wave_direction",
    "swell_wave_period",
    "sea_surface_temperature",
)
WEATHER_HOURLY_FIELDS = ("wind_speed_10m", "wind_direction_10m", "wind_gusts_10m")
# Daily sun times come from the same weather endpoint (no new API/key).
WEATHER_DAILY_FIELDS = ("sunrise", "sunset")

# ~0.13° is roughly 14 km — enough to move off the coast onto a marine grid point.
_SEAWARD_OFFSET_DEG = 0.13

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "forecasts"
CACHE_TTL_SECONDS = 6 * 3600
# Bumped when the cached frame shape changes (v3: swell_wave_direction /
# swell_wave_period added) so old-shape entries are never served as fresh.
CACHE_VERSION = 3


def _seaward_offset(lat: float, lon: float) -> tuple[float, float]:
    """Offset a spot's coords toward open ocean so Open-Meteo resolves a marine grid point.

    Direction is inferred from position: Tasmania and the south coast shift
    south, the east coast (lon >= 147) shifts east, the west coast
    (lon <= 125) shifts west.

    Shared with the climatology builder (Worker B): reuse this instead of
    re-implementing the offset for archive calls.
    """
    if lat <= -39.5:  # Tasmania: open ocean to the south
        dlat, dlon = -_SEAWARD_OFFSET_DEG, 0.0
    elif lon >= 147:  # east coast (QLD/NSW)
        dlat, dlon = 0.0, _SEAWARD_OFFSET_DEG
    elif lon <= 125:  # west coast (WA)
        dlat, dlon = 0.0, -_SEAWARD_OFFSET_DEG
    else:  # south coast (SA/VIC)
        dlat, dlon = -_SEAWARD_OFFSET_DEG, 0.0
    return dlat, dlon


def _round_coords(lat: float, lon: float) -> tuple[float, float]:
    dlat, dlon = _seaward_offset(lat, lon)
    return round(lat + dlat, 2), round(lon + dlon, 2)


def _cache_key(lat: float, lon: float, days: int) -> str:
    """Cache key from the *raw* spot coords (offset is a fetch detail only)."""
    return f"v{CACHE_VERSION}_{round(lat, 2):.2f}_{round(lon, 2):.2f}_{days}"


def _cache_path(lat: float, lon: float, days: int) -> Path:
    return CACHE_DIR / f"{_cache_key(lat, lon, days)}.json"


def _load_cache(lat: float, lon: float, days: int) -> tuple[dict, float] | None:
    """Return ``(data, fetched_at)`` from disk, or None if absent/corrupt.

    Legacy cache files written before the envelope format are returned with
    ``fetched_at = 0`` so they still work as a stale fallback.
    """
    p = _cache_path(lat, lon, days)
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(raw, dict) and "fetched_at" in raw and "data" in raw:
        return raw["data"], float(raw["fetched_at"])
    return raw, 0.0


def _save_cache(lat: float, lon: float, days: int, data: dict) -> None:
    """Write the cache envelope atomically (crash-safe write + rename)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    envelope = {"fetched_at": time.time(), "data": data}
    tmp = _cache_path(lat, lon, days).with_suffix(".tmp")
    tmp.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _cache_path(lat, lon, days))


def _build_normalized(marine: dict, weather: dict) -> dict:
    """Merge marine + weather hourly on ``time`` into a clean frame.

    Also carries ``daily`` sun times (``{"time", "sunrise", "sunset"}``)
    straight from the weather endpoint, plus optional per-hour
    ``sea_surface_temperature`` (C) and ``wind_gusts_10m`` (km/h) when
    the API serves them. Scoring ignores unknown fields, so old
    consumers keep working.
    """
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

    daily: dict = {}
    w_daily = weather.get("daily") or {}
    if isinstance(w_daily, dict) and w_daily.get("time"):
        daily = {
            k: w_daily.get(k)
            for k in ("time", *WEATHER_DAILY_FIELDS)
            if k in w_daily
        }

    out: dict = {"hourly": frames}
    if daily:
        out["daily"] = daily
    return out


def _fetch_open_meteo(rlat: float, rlon: float, days: int) -> dict:
    """Call both Open-Meteo endpoints and return the merged frame."""
    params: dict[str, str | int | float] = {
        "latitude": rlat,
        "longitude": rlon,
        "forecast_days": days,
    }

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        resp_m = client.get(MARINE_URL, params={**params, "hourly": ",".join(MARINE_HOURLY_FIELDS)})
        resp_m.raise_for_status()
        marine = resp_m.json()
        resp_w = client.get(
            WEATHER_URL,
            params={
                **params,
                "hourly": ",".join(WEATHER_HOURLY_FIELDS),
                "daily": ",".join(WEATHER_DAILY_FIELDS),
                "timezone": "auto",
            },
        )
        resp_w.raise_for_status()
        weather = resp_w.json()

    return _build_normalized(marine, weather)


def get_forecast(lat: float, lon: float, days: int = 7) -> dict:
    """Fetch marine + weather hourly data for a coordinate, merged on time.

    Returns a normalised frame: ``{"hourly": [{"time": ..., "wave_height": ...,
    "swell_wave_height": ..., "wind_speed_10m": ..., ...}, ...], "daily":
    {"time": [...], "sunrise": [...], "sunset": [...]}}``. Disk-cached by
    rounded coords + days: entries younger than ``CACHE_TTL_SECONDS`` are
    served directly; on a network failure the most recent cache entry
    (however old) is served as a fallback. Raises only when there is no
    usable data at all.
    """
    rlat, rlon = _round_coords(lat, lon)
    cached = _load_cache(lat, lon, days)
    if cached is not None and time.time() - cached[1] < CACHE_TTL_SECONDS:
        return cached[0]

    try:
        merged = _fetch_open_meteo(rlat, rlon, days)
    except (httpx.HTTPError, KeyError, ValueError):
        if cached is not None:
            return cached[0]
        raise

    _save_cache(lat, lon, days, merged)
    return merged


__all__ = [
    "MARINE_URL",
    "WEATHER_URL",
    "MARINE_HOURLY_FIELDS",
    "WEATHER_HOURLY_FIELDS",
    "WEATHER_DAILY_FIELDS",
    "CACHE_TTL_SECONDS",
    "CACHE_VERSION",
    "_seaward_offset",
    "get_forecast",
]
