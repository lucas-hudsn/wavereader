"""Offline tests for the UI climate charts (interpretability contract)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from ui.charts.climate import _season_bands, build_rose_fig, build_year_fig

FIXTURE = Path(__file__).parent / "fixtures" / "climate_bells.json"


@pytest.fixture()
def bells_climate():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _compat_monthly(climate):
    """Mimic ui._compat.get_climate_monthly without the backend indirection."""
    out = []
    for m in range(1, 13):
        e = climate["monthly"][str(m)]
        days, n = e["days_in_ideal_window"], e["n_days"]
        out.append({"month": m, "height_m": e["median_swell_height_m"],
                    "period_s": e["median_swell_period_s"], "days": days,
                    "n_days": n, "pct": round(100.0 * days / n, 1) if n else None})
    return out


def test_season_bands_wrap_and_boundaries():
    """Summer = Dec–Feb (wraps the axis), winter = Jun–Aug — zero-based months."""
    bands = {(lab, round(x0, 1), round(x1, 1)) for x0, x1, lab, _ in _season_bands()}
    # summer wraps: Jan–Feb at the left edge AND Dec at the right edge
    assert ("summer", -0.5, 2.5) in bands
    assert ("summer", 10.5, 12.5) in bands
    assert ("autumn", 1.5, 5.5) in bands    # Mar–May
    assert ("winter", 4.5, 8.5) in bands    # Jun–Aug
    assert ("spring", 7.5, 11.5) in bands   # Sep–Nov


def test_rose_fig_subtitles_ticks_and_ideal_markers(bells_climate):
    profile = {"rose": bells_climate["direction_rose_pct"]}
    fig = build_rose_fig(profile, "Bells Beach", ideal_dirs=["SW", "S", "SSW"])
    assert len(fig.data) == 2  # barpolar + stated-ideal markers
    subtitle = fig.layout.title.text
    assert "dominant swell SW — 28% of days" in subtitle and "top-2 carry 50%" in subtitle
    assert "◇ stated ideal" in subtitle
    assert list(fig.data[1].theta) == ["SW", "S", "SSW"]
    radial = fig.layout.polar.radialaxis
    assert all(t.endswith("%") for t in radial.ticktext)  # suffix must survive array mode


def test_rose_fig_placeholder_on_empty():
    fig = build_rose_fig({}, "Nowhere")
    assert len(fig.data) == 0


def test_year_fig_pct_axis_and_window(bells_climate):
    monthly = _compat_monthly(bells_climate)
    fig = build_year_fig(monthly, "Bells Beach", window_label="4–12 ft")
    bar = fig.data[0]
    assert bar.y[9] == pytest.approx(35 / 155 * 100, abs=0.05)   # Oct
    assert max(bar.y) <= 100.0
    assert "4–12 ft" in fig.layout.yaxis.title.text
    assert fig.layout.yaxis.range[0] == 0
    # season annotations present, incl. the wrapped SUMMER label over Jan–Feb
    texts = [a.text for a in fig.layout.annotations]
    assert texts.count("SUMMER") == 2  # Jan–Feb + Dec wrap
    assert "WINTER" in texts and "AUTUMN" in texts and "SPRING" in texts


def test_year_fig_placeholder_and_day_fallback(bells_climate):
    assert len(build_year_fig(None).data) == 0
    stripped = [{k: v for k, v in m.items() if k not in ("pct", "n_days")}
                for m in _compat_monthly(bells_climate)]
    fig = build_year_fig(stripped, "Bells")
    assert fig.data[0].y[9] == pytest.approx(35.0)  # falls back to 5-yr day counts
