"""Offline tests for wavereader.seafloor (slope math, None-skipping).

All grids are synthetic — no network. ``get_grid`` is monkeypatched where
``get_seafloor`` is exercised.
"""

import math

import pytest

from wavereader import seafloor as sf


def _synthetic_grid(n=5, center=(-38.37, 144.28), ramp=None, none_at=()):
    """Build a grid via the real _deg_offsets; elev optional ramp fn(i, j)."""
    dlat, dlon = sf._deg_offsets(center[0], 1.2, n)
    lats = [round(center[0] + d, 5) for d in dlat]
    lngs = [round(center[1] + d, 5) for d in dlon]
    elev = []
    for i in range(n):
        for j in range(n):
            v = float(ramp(i, j)) if ramp else -10.0
            elev.append(None if (i, j) in none_at else v)
    return {
        "lats": lats, "lngs": lngs, "elev": elev, "n": n,
        "radius_km": 1.2, "dataset": "test",
        "center": {"lat": center[0], "lng": center[1]},
    }


# ---- Step math ----

def _degree_grid(n=5, center=(-38.37, 144.28), step_deg=0.01, ramp=None, none_at=()):
    """Grid with EQUAL degree spacing on both axes (not square in km).

    This is the case the v1 slope bug got wrong: at lat -38°, 0.01° of
    longitude is only ~0.87 km while 0.01° of latitude is 1.11 km.
    """
    lats = [round(center[0] + (i - n // 2) * step_deg, 5) for i in range(n)]
    lngs = [round(center[1] + (j - n // 2) * step_deg, 5) for j in range(n)]
    elev = []
    for i in range(n):
        for j in range(n):
            v = float(ramp(i, j)) if ramp else -10.0
            elev.append(None if (i, j) in none_at else v)
    return {
        "lats": lats, "lngs": lngs, "elev": elev, "n": n,
        "radius_km": 1.2, "dataset": "test",
        "center": {"lat": center[0], "lng": center[1]},
    }


# ---- Step math ----

def test_lon_step_scaled_by_cos_lat():
    grid = _degree_grid()
    lat_step, lon_step = sf._grid_steps_km(grid)
    assert lat_step == pytest.approx(0.01 * 111.0, rel=1e-6)
    assert lon_step == pytest.approx(0.01 * 111.0 * math.cos(math.radians(-38.37)), rel=1e-6)
    assert lon_step < lat_step  # meridians converge away from the equator


def test_square_grid_steps_approx_equal():
    # Grids built by _deg_offsets are square in km by construction;
    # per-axis derivation must recover (approximately) equal steps.
    grid = _synthetic_grid()
    lat_step, lon_step = sf._grid_steps_km(grid)
    assert lat_step == pytest.approx(0.6, abs=0.02)
    assert lon_step == pytest.approx(0.6, abs=0.02)


def test_lon_ramp_scores_steeper_than_equal_lat_ramp():
    """Equal m-per-degree ramps on a degree grid: E–W must score steeper.

    At lat -38° the same 5 m/cell over 0.01° is a steeper gradient along
    longitude (~0.87 km) than along latitude (1.11 km). The v1 bug (lat
    step reused for both axes) reported them equal.
    """
    ramp_ew = lambda i, j: -10.0 - 5.0 * j   # varies along longitude
    ramp_ns = lambda i, j: -10.0 - 5.0 * i   # varies along latitude
    ew = sf.analyze_grid(_degree_grid(ramp=ramp_ew))["stats"]
    ns = sf.analyze_grid(_degree_grid(ramp=ramp_ns))["stats"]
    assert ew["max_slope_m_per_km"] == pytest.approx(5.0 / (0.01 * 111.0 * math.cos(math.radians(-38.37))), rel=0.05)
    assert ns["max_slope_m_per_km"] == pytest.approx(5.0 / (0.01 * 111.0), rel=0.05)
    assert ew["max_slope_m_per_km"] > ns["max_slope_m_per_km"] * 1.1


# ---- None handling ----

def test_analyze_grid_skips_none_cells():
    grid = _synthetic_grid(none_at={(0, 0), (2, 2), (4, 4)})
    out = sf.analyze_grid(grid)
    assert "stats" in out
    assert out["stats"]["points"] == 25 - 3
    assert out["stats"]["center_elev_m"] is None  # centre cell is None


def test_analyze_grid_empty():
    assert sf.analyze_grid({"elev": [None, None], "n": 2}) == {"error": "Empty seafloor grid"}
    assert sf.analyze_grid({"elev": [], "n": 3}) == {"error": "Empty seafloor grid"}


def test_analyze_grid_stats_shape():
    out = sf.analyze_grid(_synthetic_grid())
    stats = out["stats"]
    assert stats["shelf_class"] in (
        "steep reef edge / drop-off",
        "moderately sloping reef/shelf",
        "shallow, gently shelving platform",
        "gradual sandy shelf",
    )
    assert "Seafloor" in out["markdown"]


# ---- get_seafloor without network ----

def test_get_seafloor_uses_grid(monkeypatch):
    grid = _synthetic_grid()
    monkeypatch.setattr(sf, "get_grid", lambda *a, **k: grid)
    out = sf.get_seafloor(-38.37, 144.28)
    assert out["grid"] is grid
    assert out["stats"]["points"] == 25
    assert isinstance(out["analysis"], str)
