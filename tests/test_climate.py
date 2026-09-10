"""Offline tests for wavereader.climate (Worker B slice). No network."""

import json
import sys
from pathlib import Path

# Bootstrap: repo root on sys.path so `wavereader.climate` imports without
# requiring Worker A's `wavereader/__init__.py` (absent on v2-climate branch).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from wavereader.climate import (
    COMPASS16,
    audit_break,
    break_climate,
    build_profile,
    climate_rose_fig,
    compute_monthly_stats,
    compute_rose,
    direction_rose,
    direction_to_bin,
    dominant_directions,
    filter_existing_slugs,
    ideal_window_label,
    load_climate,
    monthly_medians,
    monthly_window_pct,
    month_to_season,
    rose_top_share,
    slugify,
    summarize,
    top_months_by_window,
    top_rose_bins,
)

FIXTURE = Path(__file__).parent / "fixtures" / "climate_bells.json"

BELLS_BREAK = {
    "id": "Bells Beach | Victoria | Surf Coast",
    "name": "Bells Beach",
    "idealSwell": {"direction": ["SW", "S", "SSW"], "sizeRangeFt": {"min": 4, "max": 12}},
    "bestSeason": ["autumn", "winter"],
}


@pytest.fixture()
def bells_climate():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_direction_to_bin_edges():
    assert direction_to_bin(0) == "N"
    assert direction_to_bin(360) == "N"
    assert direction_to_bin(22.5) == "NNE"
    assert direction_to_bin(225) == "SW"
    assert direction_to_bin(359) == "N"


def test_compute_rose_known_distribution():
    rose = compute_rose([90.0] * 50 + [180.0] * 25 + [None, None])
    assert rose["E"] == pytest.approx(66.67, abs=0.01)
    assert rose["S"] == pytest.approx(33.33, abs=0.01)
    assert sum(rose.values()) == pytest.approx(100.0, abs=0.1)
    assert set(rose) == set(COMPASS16)


def test_compute_rose_empty_and_nulls():
    assert all(v == 0.0 for v in compute_rose([]).values())
    assert all(v == 0.0 for v in compute_rose([None, None]).values())
    assert sum(compute_rose([None, 45.0]).values()) == pytest.approx(100.0)


def test_direction_rose_accessor(bells_climate):
    rose = direction_rose(bells_climate)
    assert set(rose) == set(COMPASS16)
    assert sum(rose.values()) == pytest.approx(100.0, abs=0.5)
    assert top_rose_bins(bells_climate, 3) == ["SW", "S", "SSW"]


def test_monthly_medians_accessor(bells_climate):
    med = monthly_medians(bells_climate)
    assert set(med) == set(range(1, 13))
    assert med[6]["median_swell_height_m"] == pytest.approx(2.5)
    assert med[1]["median_swell_period_s"] == pytest.approx(10.5)


def test_monthly_stats_grouping_and_window():
    dates = ["2021-01-05", "2021-01-20", "2021-06-10", "bad-date"]
    # window 1.0m..2.0m
    stats = compute_monthly_stats(dates, [1.5, 5.0, 1.2], [10.0, 11.0, 12.0], 1.0, 2.0)
    assert stats[1]["median_swell_height_m"] == pytest.approx(3.25)
    assert stats[1]["days_in_ideal_window"] == 1
    assert stats[6]["days_in_ideal_window"] == 1
    assert stats[6]["n_days"] == 1
    assert stats[2]["n_days"] == 0
    assert stats[2]["median_swell_height_m"] is None


def test_top_months_by_window(bells_climate):
    assert top_months_by_window(bells_climate, 3) == [6, 7, 5]


def test_monthly_window_pct(bells_climate):
    pct = monthly_window_pct(bells_climate)
    assert set(pct) == set(range(1, 13))
    assert pct[10] == pytest.approx(22.6, abs=0.01)  # 35/155, rounded to 0.1
    assert pct[6] == pytest.approx(53.3, abs=0.01)   # 80/150
    empty = {"monthly": {"3": {"days_in_ideal_window": 0, "n_days": 0}}}
    assert monthly_window_pct(empty)[3] is None


def test_dominant_directions_and_top_share(bells_climate):
    assert dominant_directions(bells_climate, 2) == [("SW", 28.0), ("S", 22.0)]
    assert rose_top_share(bells_climate, 2) == pytest.approx(50.0)
    assert rose_top_share({"direction_rose_pct": {}}) == 0.0


def test_ideal_window_label(bells_climate):
    assert ideal_window_label(bells_climate) == "4–12 ft"
    assert ideal_window_label({"ideal_window_ft": {"min": None, "max": None}}) == ""
    assert ideal_window_label({}) == ""


def test_summarize_digest(bells_climate):
    s = summarize(bells_climate)
    assert s["ideal_window_ft"] == "4–12 ft"
    assert s["dominant_directions"] == [["SW", 28.0], ["S", 22.0]]
    assert s["top_directions_share_pct"] == pytest.approx(50.0)
    # by share of in-window days: 6 (53.3%) > 7 (48.4%) > 5 (45.2%)
    assert s["best_months_by_share"] == [6, 7, 5]
    assert set(s["monthly_window_pct"]) == set(range(1, 13))
    assert s["monthly_window_pct"][6] == pytest.approx(53.3, abs=0.1)
    json.dumps(s)  # must stay JSON-serializable for the agent tool surface


def test_month_to_season():
    assert month_to_season(1) == "summer"
    assert month_to_season(4) == "autumn"
    assert month_to_season(7) == "winter"
    assert month_to_season(10) == "spring"
    with pytest.raises(ValueError):
        month_to_season(13)


def test_audit_agreement_bells(bells_climate):
    # Dataset SW/S/SSW == rose top-3; autumn/winter covers top months 6,7,5.
    assert audit_break(BELLS_BREAK, bells_climate) == []


def test_audit_direction_disagreement(bells_climate):
    bad = {**BELLS_BREAK, "idealSwell": {"direction": ["N", "NE"]}}
    findings = audit_break(bad, bells_climate)
    by_field = {f["field"]: f for f in findings}
    assert by_field["idealSwell.direction"]["severity"] == "high"
    assert by_field["idealSwell.direction"]["dataset_value"] == ["N", "NE"]
    assert by_field["idealSwell.direction"]["climate_value"] == ["SW", "S", "SSW"]
    # season still agrees -> no season finding
    assert "bestSeason" not in by_field


def test_audit_season_disagreement(bells_climate):
    bad = {**BELLS_BREAK, "bestSeason": ["summer"]}
    findings = audit_break(bad, bells_climate)
    by_field = {f["field"]: f for f in findings}
    assert by_field["bestSeason"]["severity"] == "medium"
    assert by_field["bestSeason"]["dataset_value"] == ["summer"]
    assert by_field["bestSeason"]["climate_value"] == [6, 7, 5]
    assert "idealSwell.direction" not in by_field


def test_audit_no_data_returns_empty():
    empty = {"n_valid_direction": 0, "direction_rose_pct": {}, "monthly": {}}
    assert audit_break(BELLS_BREAK, empty) == []


def test_slugify():
    assert slugify("Bells Beach | Victoria | Surf Coast") == "bells-beach-victoria-surf-coast"
    assert slugify("Avoca Beach | New South Wales | Central Coast") == (
        "avoca-beach-new-south-wales-central-coast"
    )


def test_load_climate_fixture(bells_climate):
    loaded = load_climate("climate_bells", Path(__file__).parent / "fixtures")
    assert loaded == bells_climate
    with pytest.raises(FileNotFoundError):
        load_climate("nope", Path(__file__).parent / "fixtures")


def test_break_climate_prefers_embedded(bells_climate, tmp_path):
    break_ = dict(BELLS_BREAK, state="Victoria", region="Surf Coast", climate=bells_climate)
    # embedded copy wins even when the fallback dir holds nothing
    assert break_climate(break_, tmp_path) == bells_climate


def test_break_climate_file_fallback(bells_climate, tmp_path):
    import shutil

    shutil.copy(FIXTURE, tmp_path / "bells-beach-victoria-surf-coast.json")
    break_ = {k: v for k, v in BELLS_BREAK.items() if k != "id"}
    break_["state"] = "Victoria"
    break_["region"] = "Surf Coast"
    assert break_climate(break_, tmp_path) == bells_climate
    with pytest.raises(FileNotFoundError):
        break_climate({"name": "Nowhere", "state": "X", "region": "Y"}, tmp_path)


def test_filter_existing_slugs_resumable(tmp_path):
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    assert filter_existing_slugs(["a", "b"], tmp_path) == ["b"]
    assert filter_existing_slugs(["a", "b"], tmp_path, overwrite=True) == ["a", "b"]


def test_build_profile_roundtrip():
    dates = ["2021-01-01", "2021-01-02", "2021-07-01"]
    prof = build_profile(
        slug="x", break_id="X", name="X", latitude=-38.5, longitude=144.3,
        start="2021-01-01", end="2021-12-31", dates=dates,
        heights_m=[1.5, None, 2.0], directions_deg=[225.0, 225.0, None],
        periods_s=[12.0, 11.0, 13.0], window_min_ft=4, window_max_ft=12,
    )
    assert prof["n_days"] == 3
    assert prof["n_valid_direction"] == 2
    assert prof["direction_rose_pct"]["SW"] == pytest.approx(100.0)
    assert prof["monthly"]["1"]["n_days"] == 2


def test_climate_rose_fig(bells_climate):
    fig = climate_rose_fig(bells_climate, "Bells Beach")
    assert len(fig.data) == 1
    assert len(fig.data[0].r) == 16
    assert list(fig.data[0].theta) == COMPASS16
    assert max(fig.data[0].r) == pytest.approx(28.0)
