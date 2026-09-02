"""Unit tests for wavereader.forecasts — cache, offsets, merge, fallbacks."""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import httpx
import pytest

from wavereader import forecasts


# ---------------------------------------------------------------------------
# Seaward offsets
# ---------------------------------------------------------------------------

def test_offset_east_coast_moves_east():
    # Snapper Rocks (QLD): seaward is east, not the old fixed south-east
    rlat, rlon = forecasts._round_coords(-28.173, 153.556)
    assert rlon > 153.556
    assert rlat == pytest.approx(-28.173, abs=0.01)


def test_offset_west_coast_moves_west():
    # Margaret River region (WA): seaward is west
    rlat, rlon = forecasts._round_coords(-33.95, 115.0)
    assert rlon < 115.0
    assert rlat == pytest.approx(-33.95, abs=0.01)


def test_offset_south_coast_moves_south():
    # Bells Beach (VIC): seaward is south
    rlat, rlon = forecasts._round_coords(-38.37, 144.25)
    assert rlat < -38.37
    assert rlon == pytest.approx(144.25, abs=0.01)


def test_offset_tasmania_moves_south():
    rlat, _ = forecasts._round_coords(-41.0, 145.0)
    assert rlat < -41.0


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------

@pytest.fixture
def cache_env(tmp_path, monkeypatch):
    """Point the cache at a temp dir and freeze time deterministically."""
    monkeypatch.setattr(forecasts, "CACHE_DIR", tmp_path)
    return tmp_path


def test_cache_roundtrip_and_ttl(cache_env):
    now = time.time()
    with patch.object(forecasts, "_fetch_open_meteo", return_value={"hourly": [{"time": "t"}]}) as fetch:
        first = forecasts.get_forecast(-28.0, 153.0, days=2)
        assert fetch.call_count == 1
        assert first["hourly"][0]["time"] == "t"

        # Envelope has a timestamp
        raw = json.loads(next(cache_env.glob("*.json")).read_text())
        assert raw["fetched_at"] == pytest.approx(now, abs=30)

        # Fresh cache: served without a second network call
        forecasts.get_forecast(-28.0, 153.0, days=2)
        assert fetch.call_count == 1


def test_stale_cache_is_refetched(cache_env):
    with patch.object(forecasts, "_fetch_open_meteo", side_effect=[{"hourly": [{"v": 1}]}, {"hourly": [{"v": 2}]}]):
        forecasts.get_forecast(-28.0, 153.0, days=2)

    # Age the cache entry beyond the TTL
    p = next(cache_env.glob("*.json"))
    raw = json.loads(p.read_text())
    raw["fetched_at"] = time.time() - forecasts.CACHE_TTL_SECONDS - 1
    p.write_text(json.dumps(raw))

    with patch.object(forecasts, "_fetch_open_meteo", return_value={"hourly": [{"v": 3}]}) as fetch:
        refreshed = forecasts.get_forecast(-28.0, 153.0, days=2)
    assert fetch.call_count == 1
    assert refreshed["hourly"][0]["v"] == 3


def test_http_failure_falls_back_to_stale_cache(cache_env):
    with patch.object(forecasts, "_fetch_open_meteo", return_value={"hourly": [{"v": 1}]}):
        forecasts.get_forecast(-28.0, 153.0, days=2)

    # Age it, then make the network fail
    p = next(cache_env.glob("*.json"))
    raw = json.loads(p.read_text())
    raw["fetched_at"] = 0.0
    p.write_text(json.dumps(raw))

    def boom(*args, **kwargs):
        raise httpx.ConnectError("network down")

    with patch.object(forecasts, "_fetch_open_meteo", side_effect=boom):
        served = forecasts.get_forecast(-28.0, 153.0, days=2)
    assert served["hourly"][0]["v"] == 1


def test_http_failure_no_cache_raises(cache_env):
    def boom(*args, **kwargs):
        raise httpx.ConnectError("network down")

    with patch.object(forecasts, "_fetch_open_meteo", side_effect=boom):
        with pytest.raises(httpx.ConnectError):
            forecasts.get_forecast(-28.0, 153.0, days=2)


def test_corrupt_cache_is_ignored(cache_env):
    cache_env.joinpath("-28.00_153.00_2.json").write_text("{not json")
    with patch.object(forecasts, "_fetch_open_meteo", return_value={"hourly": []}) as fetch:
        forecasts.get_forecast(-28.0, 153.0, days=2)
    assert fetch.call_count == 1


def test_legacy_cache_format_still_loads(cache_env):
    # Pre-envelope files (plain frame) are accepted and treated as stale;
    # served when the network fails.
    cache_env.joinpath("-28.00_153.00_2.json").write_text(json.dumps({"hourly": [{"legacy": True}]}))

    def boom(*args, **kwargs):
        raise httpx.ConnectError("network down")

    with patch.object(forecasts, "_fetch_open_meteo", side_effect=boom):
        served = forecasts.get_forecast(-28.0, 153.0, days=2)
    assert served["hourly"][0]["legacy"] is True


def test_cache_key_includes_days(cache_env):
    with patch.object(forecasts, "_fetch_open_meteo", return_value={"hourly": []}):
        forecasts.get_forecast(-28.0, 153.0, days=2)
        forecasts.get_forecast(-28.0, 153.0, days=7)
    keys = {p.name for p in cache_env.glob("*.json")}
    assert len(keys) == 2


# ---------------------------------------------------------------------------
# _build_normalized
# ---------------------------------------------------------------------------

def _marine_payload(times, heights):
    return {"hourly": {
        "time": times,
        "wave_height": heights,
        "wave_period": [10.0] * len(times),
        "wave_direction": [135.0] * len(times),
        "wind_wave_height": [0.5] * len(times),
        "swell_wave_height": [1.0] * len(times),
    }}


def _weather_payload(times):
    return {"hourly": {
        "time": times,
        "wind_speed_10m": [18.5] * len(times),
        "wind_direction_10m": [180.0] * len(times),
    }}


def test_build_normalized_merges_on_time():
    times = ["2024-01-01T00:00", "2024-01-01T01:00"]
    merged = forecasts._build_normalized(_marine_payload(times, [1.2, 1.4]), _weather_payload(times))
    rows = merged["hourly"]
    assert len(rows) == 2
    assert rows[0]["wave_height"] == 1.2
    assert rows[0]["wind_speed_10m"] == 18.5
    assert rows[1]["wave_period"] == 10.0


def test_build_normalized_missing_weather_hour():
    marine_times = ["2024-01-01T00:00", "2024-01-01T01:00"]
    weather_times = ["2024-01-01T00:00"]  # weather ends an hour early
    merged = forecasts._build_normalized(
        _marine_payload(marine_times, [1.2, 1.4]), _weather_payload(weather_times)
    )
    rows = merged["hourly"]
    assert "wind_speed_10m" in rows[0]
    assert "wind_speed_10m" not in rows[1]


def test_build_normalized_keeps_nulls():
    times = ["2024-01-01T00:00", "2024-01-01T01:00"]
    merged = forecasts._build_normalized(_marine_payload(times, [1.2, None]), _weather_payload(times))
    assert merged["hourly"][1]["wave_height"] is None
