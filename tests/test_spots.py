"""Unit tests for wavereader.spots — data layer."""

from pathlib import Path

import pytest

from wavereader.spots import (
    AdditionalDetails,
    Break,
    Coordinates,
    IdealSwell,
    IdealWind,
    find_spots,
    get_spot,
    load_breaks,
)


# ---------------------------------------------------------------------------
# load_breaks
# ---------------------------------------------------------------------------

def test_load_breaks_count():
    breaks = load_breaks()
    assert len(breaks) == 100


def test_load_breaks_all_have_fields():
    breaks = load_breaks()
    for b in breaks:
        assert b.name
        assert b.region
        assert b.coordinates.lat is not None
        assert b.coordinates.lng is not None
        assert b.ideal_swell.size_ft_min < b.ideal_swell.size_ft_max
        assert b.ideal_wind.strength_kt_max > 0
        assert b.additional_details.skill_level


# ---------------------------------------------------------------------------
# find_spots
# ---------------------------------------------------------------------------

def test_find_spots_by_name():
    results = find_spots(query="Snapper")
    assert all("Snapper" in r.name for r in results)


def test_find_spots_by_region():
    results = find_spots(region="QLD")
    assert all(r.region == "QLD" for r in results)
    assert len(results) > 0


def test_find_spots_by_skill():
    results = find_spots(region="QLD", skill="beginner")
    assert all("beginner" in r.additional_details.skill_level.lower() for r in results)


def test_find_spots_limits():
    results = find_spots(query="", region="NSW", limit=3)
    assert len(results) <= 3


def test_find_spots_empty_query_returns_all():
    results = find_spots(query="", limit=100)
    assert len(results) == 100


def test_find_spots_no_match():
    results = find_spots(query="NonexistentBreakXyz")
    assert results == []


# ---------------------------------------------------------------------------
# get_spot
# ---------------------------------------------------------------------------

def test_get_spot_existing():
    spot = get_spot("Snapper Rocks", "QLD")
    assert spot is not None
    assert spot.name == "Snapper Rocks"
    assert spot.region == "QLD"


def test_get_spot_missing():
    spot = get_spot("Nonexistent", "XX")
    assert spot is None


# ---------------------------------------------------------------------------
# Pydantic validation
# ---------------------------------------------------------------------------

def test_break_round_trip():
    b = load_breaks()[0]
    data = b.model_dump()
    restored = Break.model_validate(data)
    assert restored.name == b.name


def test_break_invalid_region():
    with pytest.raises(Exception):
        Break.model_validate({
            "name": "Bad",
            "region": "XX",
            "short_description": "x",
            "coordinates": {"lat": -33.0, "lng": 151.0},
            "ideal_swell": {"size_ft_min": 2.0, "size_ft_max": 5.0, "direction": "SE"},
            "ideal_wind": {"strength_kt_max": 15.0, "direction": "SW"},
            "ideal_tide": "mid",
            "additional_details": {
                "break_type": "beach",
                "break_direction": "left",
                "break_surface": "sand",
                "bottom_type": "sand",
                "skill_level": "beginner",
                "best_season": "summer",
                "hazards": "rips",
                "other_notes": "x",
            },
        })


def test_break_invalid_coords():
    with pytest.raises(Exception):
        Break.model_validate({
            "name": "Bad",
            "region": "NSW",
            "short_description": "x",
            "coordinates": {"lat": 0.0, "lng": 0.0},
            "ideal_swell": {"size_ft_min": 2.0, "size_ft_max": 5.0, "direction": "SE"},
            "ideal_wind": {"strength_kt_max": 15.0, "direction": "SW"},
            "ideal_tide": "mid",
            "additional_details": {
                "break_type": "beach",
                "break_direction": "left",
                "break_surface": "sand",
                "bottom_type": "sand",
                "skill_level": "beginner",
                "best_season": "summer",
                "hazards": "rips",
                "other_notes": "x",
            },
        })


def test_break_swell_min_lt_max():
    with pytest.raises(Exception):
        Break.model_validate({
            "name": "Bad",
            "region": "NSW",
            "short_description": "x",
            "coordinates": {"lat": -33.0, "lng": 151.0},
            "ideal_swell": {"size_ft_min": 5.0, "size_ft_max": 3.0, "direction": "SE"},
            "ideal_wind": {"strength_kt_max": 15.0, "direction": "SW"},
            "ideal_tide": "mid",
            "additional_details": {
                "break_type": "beach",
                "break_direction": "left",
                "break_surface": "sand",
                "bottom_type": "sand",
                "skill_level": "beginner",
                "best_season": "summer",
                "hazards": "rips",
                "other_notes": "x",
            },
        })


# ---------------------------------------------------------------------------
# Region bounding-box validation
# ---------------------------------------------------------------------------

def test_bells_beach_vic():
    """Bells Beach is the VIC validation target from the roadmap."""
    b = get_spot("Bells Beach", "VIC")
    assert b is not None
    assert -39.0 <= b.coordinates.lat <= -36.0


def test_snapper_rocks_qld():
    b = get_spot("Snapper Rocks", "QLD")
    assert b is not None
    assert -29.0 <= b.coordinates.lat <= -10.0
