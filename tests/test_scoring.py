"""Unit tests for wavereader.scoring — deterministic surf-quality scoring."""

from __future__ import annotations

import pytest

from wavereader.scoring import (
    _angular_diff,
    _dir_to_deg,
    _score_period,
    _score_swell_direction,
    _score_swell_size,
    _score_wind,
    rank_spots_this_week,
    score_hour,
    score_week,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SPOT = {
    "name": "Test Spot",
    "region": "QLD",
    "ideal_swell": {"size_ft_min": 3, "size_ft_max": 8, "direction": "SE"},
    "ideal_wind": {"strength_kt_max": 10, "direction": "S"},
}


# ---------------------------------------------------------------------------
# Direction parsing
# ---------------------------------------------------------------------------

def test_dir_to_deg_simple():
    assert _dir_to_deg("N") == 0
    assert _dir_to_deg("E") == 90
    assert _dir_to_deg("S") == 180
    assert _dir_to_deg("W") == 270
    assert _dir_to_deg("SW") == 225


def test_dir_to_deg_compound():
    # W/SW = midpoint of 270 and 225 = 247.5
    assert _dir_to_deg("W/SW") == 247.5
    # E/NE = midpoint of 90 and 45 = 67.5
    assert _dir_to_deg("E/NE") == 67.5


# ---------------------------------------------------------------------------
# Angular diff
# ---------------------------------------------------------------------------

def test_angular_diff_zero():
    assert _angular_diff(0, 0) == 0


def test_angular_diff_symmetric():
    assert _angular_diff(45, 315) == 90


def test_angular_diff_wrap():
    assert _angular_diff(350, 10) == 20
    assert _angular_diff(10, 350) == 20


# ---------------------------------------------------------------------------
# Swell size scoring
# ---------------------------------------------------------------------------

def test_swell_size_in_ideal():
    # 4 ft ideal → ~1.22 m; 5 ft → ~1.52 m
    spot = {
        "ideal_swell": {"size_ft_min": 4, "size_ft_max": 5, "direction": "SE"},
        "ideal_wind": {"strength_kt_max": 10, "direction": "S"},
    }
    assert score_hour(1.4, 10, 5, 135, spot)["components"]["swell_size"] == 10.0


def test_swell_size_outside_low():
    spot = {
        "ideal_swell": {"size_ft_min": 4, "size_ft_max": 5, "direction": "SE"},
        "ideal_wind": {"strength_kt_max": 10, "direction": "S"},
    }
    # just below the extended cutoff (~0.92 m)
    s = score_hour(0.8, 10, 5, 135, spot)["components"]["swell_size"]
    assert s < 10.0 and s > 0.0


def test_swell_size_outside_high():
    spot = {
        "ideal_swell": {"size_ft_min": 4, "size_ft_max": 5, "direction": "SE"},
        "ideal_wind": {"strength_kt_max": 10, "direction": "S"},
    }
    # just above the extended cutoff (~1.82 m)
    s = score_hour(1.8, 10, 5, 135, spot)["components"]["swell_size"]
    assert s < 10.0 and s > 0.0


def test_swell_size_far_outside_zero():
    spot = {
        "ideal_swell": {"size_ft_min": 4, "size_ft_max": 5, "direction": "SE"},
        "ideal_wind": {"strength_kt_max": 10, "direction": "S"},
    }
    assert score_hour(3.0, 10, 5, 135, spot)["components"]["swell_size"] == 0.0


# ---------------------------------------------------------------------------
# Swell direction scoring
# ---------------------------------------------------------------------------

def test_swell_direction_perfect_match():
    spot = {
        "ideal_swell": {"size_ft_min": 3, "size_ft_max": 8, "direction": "SE"},
        "ideal_wind": {"strength_kt_max": 10, "direction": "S"},
    }
    # SE = 135°
    assert score_hour(1.5, 10, 5, 135, spot)["components"]["swell_direction"] == 10.0


def test_swell_direction_opposite():
    spot = {
        "ideal_swell": {"size_ft_min": 3, "size_ft_max": 8, "direction": "SE"},
        "ideal_wind": {"strength_kt_max": 10, "direction": "S"},
    }
    # SE (135) vs NW (315) → 180° diff → 0
    assert score_hour(1.5, 10, 5, 315, spot)["components"]["swell_direction"] == 0.0


# ---------------------------------------------------------------------------
# Wind scoring
# ---------------------------------------------------------------------------

def test_wind_perfect_offshore():
    spot = {
        "ideal_wind": {"strength_kt_max": 10, "direction": "N"},
        "ideal_swell": {"size_ft_min": 3, "size_ft_max": 8, "direction": "SE"},
    }
    # calm wind from N
    s = score_hour(1.5, 10, 0, 0, spot)["components"]["wind"]
    assert s == 10.0


def test_wind_opposite_direction():
    spot = {
        "ideal_wind": {"strength_kt_max": 10, "direction": "N"},
        "ideal_swell": {"size_ft_min": 3, "size_ft_max": 8, "direction": "SE"},
    }
    # strong wind from S (180° away from N)
    s = score_hour(1.5, 10, 20, 180, spot)["components"]["wind"]
    assert s == 0.0


def test_wind_speed_capped():
    spot = {
        "ideal_wind": {"strength_kt_max": 10, "direction": "N"},
        "ideal_swell": {"size_ft_min": 3, "size_ft_max": 8, "direction": "SE"},
    }
    # wind above max speed, perfect direction → speed=0, dir=10 → weighted 5.0
    s = score_hour(1.5, 10, 12, 0, spot)["components"]["wind"]
    assert s == 5.0


# ---------------------------------------------------------------------------
# Period scoring
# ---------------------------------------------------------------------------

def test_period_short():
    assert _score_period(4.0) == 0.0


def test_period_great():
    assert _score_period(14.0) == 10.0


def test_period_too_long():
    # Very long periods (storm swells) still score high but not perfect
    assert _score_period(14.0) == 10.0
    assert _score_period(8.0) > _score_period(5.0)


# ---------------------------------------------------------------------------
# score_hour – composite & breakdown
# ---------------------------------------------------------------------------

def test_score_hour_shape():
    result = score_hour(1.5, 10, 5, 135, _SPOT)
    assert "score" in result
    assert "components" in result
    assert set(result["components"].keys()) == {
        "swell_size", "swell_direction", "wind", "period"
    }
    assert 0 <= result["score"] <= 10
    for v in result["components"].values():
        assert 0 <= v <= 10


def test_score_hour_contains_raw_inputs():
    result = score_hour(1.5, 10, 5, 135, _SPOT)
    assert result["wave_height_m"] == 1.5
    assert result["wave_period_s"] == 10
    assert result["wind_speed_kt"] == 5
    assert result["wind_direction_deg"] == 135


# ---------------------------------------------------------------------------
# Bells Beach sanity check (roadmap)
# ---------------------------------------------------------------------------

def test_bells_beach_swell_nw_wind_high_score():
    """Bells Beach should score well on SW swell + light NW wind."""
    bells = {
        "name": "Bells Beach",
        "region": "VIC",
        "ideal_swell": {"size_ft_min": 4, "size_ft_max": 12, "direction": "SW"},
        "ideal_wind": {"strength_kt_max": 15, "direction": "NW"},
    }
    # SW swell = 225°, light NW wind = 315°, low speed
    result = score_hour(2.0, 12, 5, 315, bells)
    assert result["score"] > 6.0


# ---------------------------------------------------------------------------
# Kirra sanity check (roadmap): long-period E
# ---------------------------------------------------------------------------

def test_kirra_long_period():
    """Kirra scores well on long-period swells."""
    kirra = {
        "name": "Kirra",
        "region": "QLD",
        "ideal_swell": {"size_ft_min": 3, "size_ft_max": 8, "direction": "SE"},
        "ideal_wind": {"strength_kt_max": 10, "direction": "S"},
    }
    long_result = score_hour(1.5, 14, 5, 135, kirra)
    short_result = score_hour(1.5, 6, 5, 135, kirra)
    assert long_result["components"]["period"] > short_result["components"]["period"]


# ---------------------------------------------------------------------------
# score_week
# ---------------------------------------------------------------------------

def test_score_week_count():
    forecast = {
        "hourly": [
            {
                "time": "2024-01-01T00:00",
                "wave_height": 1.5,
                "wave_period": 10,
                "wind_speed_10m": 10,
                "wind_direction_10m": 135,
            }
            for _ in range(24)
        ]
    }
    results = score_week(forecast, _SPOT)
    assert len(results) == 24


def test_score_week_has_time_and_score():
    forecast = {
        "hourly": [
            {
                "time": "2024-01-01T00:00",
                "wave_height": 1.5,
                "wave_period": 10,
                "wind_speed_10m": 10,
                "wind_direction_10m": 135,
            }
        ]
    }
    results = score_week(forecast, _SPOT)
    assert results[0]["time"] == "2024-01-01T00:00"
    assert "score" in results[0]


# ---------------------------------------------------------------------------
# rank_spots_this_week
# ---------------------------------------------------------------------------

def test_rank_spots_descending():
    spot_a = {
        "name": "A",
        "region": "QLD",
        "ideal_swell": {"size_ft_min": 3, "size_ft_max": 8, "direction": "SE"},
        "ideal_wind": {"strength_kt_max": 10, "direction": "S"},
    }
    spot_b = {
        "name": "B",
        "region": "NSW",
        "ideal_swell": {"size_ft_min": 2, "size_ft_max": 4, "direction": "SE"},
        "ideal_wind": {"strength_kt_max": 10, "direction": "S"},
    }
    base_forecast = {
        "hourly": [
            {
                "time": "2024-01-01T00:00",
                "wave_height": 1.5,
                "wave_period": 10,
                "wind_speed_10m": 10,
                "wind_direction_10m": 135,
            }
        ]
    }
    forecasts = {
        ("A", "QLD"): base_forecast,
        ("B", "NSW"): base_forecast,
    }
    # A gets a higher score because its ideal range includes 1.5m better
    ranked = rank_spots_this_week(forecasts, [spot_a, spot_b])
    assert len(ranked) == 2
    assert ranked[0]["best_score"] >= ranked[1]["best_score"]


def test_rank_spots_empty():
    ranked = rank_spots_this_week({}, [])
    assert ranked == []
