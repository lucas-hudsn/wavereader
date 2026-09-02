"""Unit tests for wavereader.api — FastAPI endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from wavereader.api import app

client = TestClient(app)


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "wavereader"
    assert data["status"] == "ok"


def test_list_spots():
    resp = client.get("/spots?limit=3")
    assert resp.status_code == 200
    spots = resp.json()
    assert len(spots) <= 3
    assert all("name" in s for s in spots)


def test_list_spots_by_region():
    resp = client.get("/spots?region=QLD&limit=5")
    assert resp.status_code == 200
    spots = resp.json()
    assert all(s["region"] == "QLD" for s in spots)


def test_get_spot():
    resp = client.get("/spots/Snapper Rocks?region=QLD")
    assert resp.status_code == 200
    spot = resp.json()
    assert spot["name"] == "Snapper Rocks"
    assert spot["region"] == "QLD"


def test_get_spot_not_found():
    resp = client.get("/spots/Nonexistent?region=XX")
    assert resp.status_code == 404


def _fake_forecast(lat: float, lon: float, days: int = 7) -> dict:
    """Offline stand-in for Open-Meteo so tests never hit the network."""
    return {
        "hourly": [
            {
                "time": f"2024-01-01T{h:02d}:00",
                "wave_height": 1.5,
                "wave_period": 10,
                "wave_direction": 135,
                "wind_speed_10m": 10,
                "wind_direction_10m": 135,
            }
            for h in range(24)
        ]
    }


def test_forecast():
    with patch("wavereader.forecasts.get_forecast", side_effect=_fake_forecast):
        resp = client.get("/forecast?spot=Snapper Rocks&region=QLD&days=2")
    assert resp.status_code == 200
    data = resp.json()
    assert "hourly" in data
    assert len(data["hourly"]) > 0


def test_forecast_spot_not_found():
    resp = client.get("/forecast?spot=Nonexistent&region=XX")
    assert resp.status_code == 404


def test_score():
    with patch("wavereader.forecasts.get_forecast", side_effect=_fake_forecast):
        resp = client.get("/score?spot=Snapper Rocks&region=QLD&days=2")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "score" in data[0]
    assert "components" in data[0]
    assert "time" in data[0]


def test_score_spot_not_found():
    resp = client.get("/score?spot=Nonexistent&region=XX")
    assert resp.status_code == 404


def test_ask_missing_config_returns_503():
    with patch("wavereader.api.SurfAgent", side_effect=ValueError("HF_TOKEN environment variable not set")):
        resp = client.post("/ask", json={"question": "How's Snapper?"})
    assert resp.status_code == 503
    assert "HF_TOKEN" in resp.json()["detail"]


def test_ask_agent_failure_returns_502():
    with patch("wavereader.api.SurfAgent", side_effect=RuntimeError("boom")):
        resp = client.post("/ask", json={"question": "How's Snapper?"})
    assert resp.status_code == 502
