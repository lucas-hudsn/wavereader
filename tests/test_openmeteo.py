"""Offline tests for wavereader.openmeteo (cache, merge, offset contract)."""

import json
import time
from pathlib import Path

import pytest

from wavereader import openmeteo as om

FIXTURE = Path(__file__).parent / "fixtures" / "openmeteo_bells.json"


def _use_tmp_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(om, "CACHE_DIR", tmp_path)


# ---- Fetch contract ----

def test_marine_fields_include_swell_components():
    assert "swell_wave_direction" in om.MARINE_HOURLY_FIELDS
    assert "swell_wave_period" in om.MARINE_HOURLY_FIELDS
    assert "swell_wave_height" in om.MARINE_HOURLY_FIELDS


def test_cache_version_bumped():
    # Old-shape (v2, no swell_* fields) cache must never serve as fresh.
    assert om.CACHE_VERSION == 3


# ---- Seaward offset (Worker B reuse contract) ----

@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        (-28.17, 153.55, (0.0, 0.13)),    # east coast → east
        (-33.80, 115.00, (0.0, -0.13)),   # west coast → west
        (-35.00, 138.00, (-0.13, 0.0)),   # south coast SA → south
        (-38.37, 144.28, (-0.13, 0.0)),   # Surf Coast VIC → south
        (-42.90, 147.30, (-0.13, 0.0)),   # Tasmania → south
    ],
)
def test_seaward_offset_directions(lat, lon, expected):
    assert om._seaward_offset(lat, lon) == pytest.approx(expected)


# ---- Merge ----

def test_build_normalized_merges_and_carries_daily():
    marine = {
        "hourly": {
            "time": ["2026-09-01T00:00", "2026-09-01T01:00"],
            "wave_height": [1.2, 1.3],
            "swell_wave_height": [1.0, 1.1],
            "swell_wave_direction": [180.0, 185.0],
            "swell_wave_period": [12.0, 12.5],
        }
    }
    weather = {
        "hourly": {
            "time": ["2026-09-01T00:00", "2026-09-01T01:00"],
            "wind_speed_10m": [10.0, 40.0],
            "wind_direction_10m": [0.0, 90.0],
            "wind_gusts_10m": [15.0, 50.0],
        },
        "daily": {
            "time": ["2026-09-01"],
            "sunrise": ["2026-09-01T06:00"],
            "sunset": ["2026-09-01T18:00"],
        },
    }
    out = om._build_normalized(marine, weather)
    assert len(out["hourly"]) == 2
    assert out["hourly"][0]["swell_wave_direction"] == 180.0
    assert out["hourly"][0]["wind_speed_10m"] == 10.0
    assert out["daily"]["sunrise"] == ["2026-09-01T06:00"]
    assert out["daily"]["sunset"] == ["2026-09-01T18:00"]


# ---- Disk cache, fully offline ----

def test_get_forecast_serves_fresh_cache_without_network(monkeypatch, tmp_path):
    _use_tmp_cache(monkeypatch, tmp_path)
    payload = {"hourly": [{"time": "2026-09-01T12:00", "wave_height": 1.0}], "daily": {}}
    om._save_cache(-38.37, 144.28, 3, payload)
    assert om.get_forecast(-38.37, 144.28, days=3) == payload


def test_get_forecast_falls_back_to_stale_cache(monkeypatch, tmp_path):
    _use_tmp_cache(monkeypatch, tmp_path)
    payload = {"hourly": [{"time": "2026-09-01T12:00", "wave_height": 2.0}]}
    path = om._cache_path(-38.37, 144.28, 3)
    tmp_path.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched_at": 0.0, "data": payload}))
    # httpx.Client raises (conftest) → stale fallback, not an error.
    assert om.get_forecast(-38.37, 144.28, days=3) == payload


def test_get_forecast_raises_with_no_cache_and_no_network(monkeypatch, tmp_path):
    _use_tmp_cache(monkeypatch, tmp_path)
    with pytest.raises(Exception):
        om.get_forecast(-38.37, 144.28, days=3)


def test_cache_key_embeds_version():
    assert om._cache_key(-38.37, 144.28, 3).startswith(f"v{om.CACHE_VERSION}_")


# ---- Recorded live fixture ----

def test_recorded_bells_fixture_shape():
    fc = json.loads(FIXTURE.read_text())
    assert len(fc["hourly"]) == 72
    first = fc["hourly"][0]
    for field in ("swell_wave_height", "swell_wave_direction", "swell_wave_period",
                  "wave_height", "wind_speed_10m", "wind_direction_10m"):
        assert field in first, f"fixture missing {field}"
    assert "sunrise" in fc["daily"] and "sunset" in fc["daily"]
    assert len(fc["daily"]["time"]) >= 3
