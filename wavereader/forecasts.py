"""Open-Meteo Marine + weather forecast client.

Two endpoints, merged on ``time``:

* ``marine-api.open-meteo.com`` — hourly ``wave_height`` (m), ``wave_period``
  (s), ``wave_direction`` (deg), ``swell_wave_height`` (m),
  ``wind_wave_height`` (m). Verified 2026-08-30 at Snapper Rocks: 48 hourly
  entries, no nulls, ~1.3 m @ ~6 s from ~SE. The marine endpoint does NOT
  serve wind fields.
* ``api.open-meteo.com`` — hourly ``wind_speed_10m`` (km/h; convert to knots
  for scoring) and ``wind_direction_10m`` (deg).

Grid points snap ~10 km offshore of a spot's coords (Snapper Rocks
-28.173,153.556 resolved to -28.04,153.63). Fetch slightly seaward and keep
the offset consistent across all spots.

Cache every response to disk: the demo must survive API flakiness and rate
limits. Horizon: hourly, 7 days.
"""

from __future__ import annotations

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Marine hourly fields verified against the live API 2026-08-30.
MARINE_HOURLY_FIELDS = (
    "wave_height",
    "wave_period",
    "wave_direction",
    "wind_wave_height",
    "swell_wave_height",
)
WEATHER_HOURLY_FIELDS = (
    "wind_speed_10m",
    "wind_direction_10m",
)


def get_forecast(lat: float, lon: float, days: int = 7) -> dict:
    """Fetch marine + weather hourly data for a coordinate, merged on time.

    TODO: httpx client, disk cache (keyed by rounded coords + day),
    merge the two responses, return a normalized hourly frame.
    """
    raise NotImplementedError
