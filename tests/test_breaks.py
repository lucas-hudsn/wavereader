"""Offline tests for wavereader.breaks (load, validate, resolve, filter)."""

import json

import pytest

from wavereader import breaks as br


def test_load_breaks_count_and_sort():
    breaks = br.load_breaks()
    assert len(breaks) == 238
    assert br.load_breaks.last_skipped == 0
    keys = [(b["state"], b["region"], b["name"]) for b in breaks]
    assert keys == sorted(keys)


def test_all_records_validate_strict():
    breaks = br.load_breaks(strict=True)  # raises on any invalid record
    assert len(breaks) == 238


def test_is_valid_break_rejects_garbage():
    assert not br.is_valid_break({"name": "Nope"})
    bells = br.resolve_break("Bells Beach")
    assert bells is not None and br.is_valid_break(bells)


def test_resolve_break_exact_and_case_insensitive():
    assert br.resolve_break("Bells Beach")["region"] == "Surf Coast"
    assert br.resolve_break("bells beach")["name"] == "Bells Beach"
    assert br.resolve_break("BELLS BEACH", region="surf coast")["name"] == "Bells Beach"


def test_resolve_break_fuzzy_and_scoped():
    assert br.resolve_break("bells")["name"] == "Bells Beach"
    # Unknown region falls back to the global pool.
    assert br.resolve_break("Bells Beach", region="No Such Region")["name"] == "Bells Beach"
    assert br.resolve_break("Bells Beach", region="Surf Coast")["name"] == "Bells Beach"
    assert br.resolve_break("definitely not a break xyz") is None
    assert br.resolve_break("") is None


def test_resolve_break_region_disambiguates():
    pool = [
        {"name": "The Pass", "region": "North", "state": "NSW"},
        {"name": "The Pass", "region": "South", "state": "NSW"},
    ]
    assert br.resolve_break("The Pass", region="south", breaks=pool)["region"] == "South"


def test_filter_breaks():
    breaks = br.load_breaks()
    vic = br.filter_breaks(breaks, state="victoria")
    assert vic and all(b["state"] == "Victoria" for b in vic)
    surf_coast = br.filter_breaks(breaks, region="Surf Coast")
    assert surf_coast and all(b["region"] == "Surf Coast" for b in surf_coast)
    assert br.filter_breaks(breaks, state="All") == breaks
    assert br.filter_breaks(breaks, skill="advanced")


def test_get_coords():
    lat, lng = br.get_coords(br.resolve_break("Bells Beach"))
    # OSM ground truth (beach feature), verified via scripts/check_coords.py
    assert lat == pytest.approx(-38.368985, abs=0.01)
    assert lng == pytest.approx(144.282452, abs=0.01)
    assert br.get_coords({}) == (None, None)
