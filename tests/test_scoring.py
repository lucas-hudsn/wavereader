"""Offline tests for scoring v2 (arc distance, logistic wind, daylight,
p75 summaries, surfable-hours rank, swell preference, monotonicity)."""

import pytest

from wavereader import scoring as sc
from wavereader.scoring import (
    daily_summary,
    enriched_to_scoring_spot,
    normalize_skill,
    rank_spots,
    score_hour,
    score_week,
    wind_cap,
)


def _spot(**over):
    spot = {
        "name": "Test",
        "region": "Test Coast",
        "break_type": "point",
        "ideal_swell": {"direction": "SW/S/SSW", "size_ft_min": 4.0, "size_ft_max": 12.0},
        "ideal_wind": {"direction": "N", "type": "offshore"},
    }
    for k, v in over.items():
        if isinstance(v, dict):
            spot[k] = {**spot[k], **v}
        else:
            spot[k] = v
    return spot


def _row(time="2026-09-01T12:00", **over):
    row = {
        "time": time,
        "wave_height": 1.5,
        "wave_period": 12.0,
        "wave_direction": 180.0,
        "wind_speed_10m": 9.0,
        "wind_direction_10m": 0.0,
    }
    row.update(over)
    return row


def _frame(times, **over):
    return {"hourly": [_row(t, **over) for t in times]}


# ---- Adapter shaping ----

def test_enriched_to_scoring_spot_carries_wind_type_and_break_type():
    b = {
        "name": "Bells Beach", "region": "Surf Coast", "breakType": "point",
        "idealSwell": {"direction": ["SW", "S"], "sizeRangeFt": {"min": 4, "max": 12}},
        "idealWind": {"direction": ["N"], "type": "offshore"},
        "skillLevel": "advanced",
    }
    spot = enriched_to_scoring_spot(b)
    assert spot["ideal_swell"]["direction"] == "SW/S"
    assert spot["ideal_wind"] == {"direction": "N", "type": "offshore"}
    assert spot["break_type"] == "point"


def test_normalize_skill():
    assert normalize_skill("pro-only") == "expert"
    assert normalize_skill("BEGINNER") == "beginner"
    assert normalize_skill("made-up") == "intermediate"
    assert normalize_skill(None) == "intermediate"


# ---- Direction arc (not cyclic mean) ----

def test_direction_arc_peaks_at_each_ideal_bearing():
    spot = _spot(ideal_swell={"direction": "E/SE"})
    at_e = sc._score_swell_direction(90.0, spot)
    at_se = sc._score_swell_direction(135.0, spot)
    at_mid = sc._score_swell_direction(112.5, spot)  # cyclic mean would peak here
    assert at_e == pytest.approx(10.0)
    assert at_se == pytest.approx(10.0)
    assert at_mid < 9.0  # dip between the two ideal bearings


def test_direction_arc_min_distance():
    # Bells-like arc: S is ideal, N is ~opposite → near zero.
    spot = _spot()
    assert sc._score_swell_direction(180.0, spot) == pytest.approx(10.0)
    assert sc._score_swell_direction(0.0, spot) < 1.0


def test_dir_to_deg_still_available_legacy():
    assert sc._dir_to_deg("E") == pytest.approx(90.0)


# ---- Wind cap table + logistic roll-off ----

@pytest.mark.parametrize(
    ("wind_type", "expected"),
    [("offshore", 18.0), ("cross-shore", 12.0), ("onshore", 8.0), ("light/variable", 10.0)],
)
def test_wind_cap_by_type(wind_type, expected):
    spot = _spot(ideal_wind={"direction": "N", "type": wind_type})
    assert wind_cap(spot, "expert") == pytest.approx(expected)


def test_wind_cap_bounded_by_skill_profile():
    spot = _spot()  # offshore → 18, but beginners cap at 12
    assert wind_cap(spot, "beginner") == pytest.approx(12.0)


def test_wind_speed_is_smooth_not_a_cliff():
    spot = _spot()  # offshore cap 18 for advanced (profile max 25)
    just_under = sc._score_wind(17.0, 0.0, spot, "advanced")
    at_cap = sc._score_wind(18.0, 0.0, spot, "advanced")
    just_over = sc._score_wind(19.0, 0.0, spot, "advanced")
    # No 10→0 cliff: adjacent knots differ by small steps.
    assert abs(just_under - at_cap) < 2.0
    assert abs(at_cap - just_over) < 2.0
    assert just_under > at_cap > just_over
    # Glassy air still excellent; howling onshore air scores ~0
    # (speed ~0 and direction 0 averaged: the composite, not speed alone).
    glassy = sc._score_wind(2.0, 0.0, spot, "advanced")
    howling_onshore = sc._score_wind(40.0, 180.0, spot, "advanced")
    assert glassy > 9.0
    assert howling_onshore < 1.0


def test_wind_monotonic_beyond_cap_property():
    """Stronger offshore-beyond-cap wind scores <= lighter wind."""
    spot = _spot()
    scores = [sc._score_wind(ws, 0.0, spot, "advanced") for ws in (18, 20, 25, 30)]
    assert scores == sorted(scores, reverse=True)


# ---- Swell-component preference ----

def test_score_week_prefers_swell_fields():
    spot = _spot()
    generic = {"hourly": [_row()]}
    swell_same = {"hourly": [_row(
        swell_wave_height=1.5, swell_wave_period=12.0, swell_wave_direction=180.0,
    )]}
    assert score_week(generic, spot) == score_week(swell_same, spot)


def test_score_week_uses_swell_values_not_generic():
    spot = _spot()
    # Generic aggregate is flat small; the real swell is overhead-high.
    frame = {"hourly": [_row(
        wave_height=1.5, wave_period=12.0, wave_direction=180.0,
        swell_wave_height=0.2, swell_wave_period=5.0, swell_wave_direction=0.0,
    )]}
    (got,) = score_week(frame, spot, daylight_only=False)
    assert got["wave_height_m"] == pytest.approx(0.2)
    assert got["wave_period_s"] == pytest.approx(5.0)
    assert got["wave_direction_deg"] == pytest.approx(0.0)


# ---- Daylight flag (all hours returned, nights never recommended) ----

def _sunny_frame():
    return {
        "hourly": [
            _row("2026-09-01T02:00"),  # night
            _row("2026-09-01T12:00"),  # day
            _row("2026-09-01T23:00"),  # night
        ],
        "daily": {
            "time": ["2026-09-01"],
            "sunrise": ["2026-09-01T06:00"],
            "sunset": ["2026-09-01T18:00"],
        },
    }


def test_score_week_returns_all_hours_with_daylight_flags():
    hours = score_week(_sunny_frame(), _spot())
    assert [h["time"] for h in hours] == [
        "2026-09-01T02:00", "2026-09-01T12:00", "2026-09-01T23:00"]
    assert [h["daylight"] for h in hours] == [False, True, False]


def test_score_week_daylight_only_drops_night():
    hours = score_week(_sunny_frame(), _spot(), daylight_only=True)
    assert [h["time"] for h in hours] == ["2026-09-01T12:00"]


def test_score_week_without_daily_flags_all_daylight():
    hours = score_week(_frame(["2026-09-01T02:00", "2026-09-01T12:00"]), _spot())
    assert len(hours) == 2
    assert all(h["daylight"] for h in hours)


def test_daylight_hours_filters_and_fails_open():
    rows = [
        {"time": "a", "score": 9, "daylight": False},
        {"time": "b", "score": 5, "daylight": True},
        {"time": "c", "score": 7},  # flag-absent legacy row counts as daylight
        "junk",
    ]
    assert [r["time"] for r in sc.daylight_hours(rows)] == ["b", "c"]
    assert sc.daylight_hours(None) == []


# ---- Daily summary (p75) ----

def test_daily_summary_is_p75():
    hours = [
        {"time": "2026-09-01T09:00", "score": 2.0},
        {"time": "2026-09-01T10:00", "score": 4.0},
        {"time": "2026-09-01T11:00", "score": 6.0},
        {"time": "2026-09-01T12:00", "score": 8.0},
        {"time": "2026-09-02T12:00", "score": 9.0},
    ]
    (d1, d2) = daily_summary(hours)
    assert d1["date"] == "2026-09-01"
    assert d1["p75"] == pytest.approx(6.5)  # linear interp between 6 and 8
    assert d1["best"] == pytest.approx(8.0)
    assert d1["n"] == 4
    assert d1["surfable_hours"] == 2
    assert d2["p75"] == pytest.approx(9.0)


def test_daily_summary_skips_flagged_night_hours():
    hours = [
        {"time": "2026-09-01T03:00", "score": 10.0, "daylight": False},
        {"time": "2026-09-01T12:00", "score": 6.0, "daylight": True},
    ]
    (d1,) = daily_summary(hours)
    assert d1["best"] == pytest.approx(6.0)
    assert d1["n"] == 1


# ---- Rank by surfable hours ----

def test_rank_spots_prefers_surfable_hours_over_single_best():
    alto = _spot(name="Alto", region="R")
    bajo = _spot(name="Bajo", region="R")
    # Alto: one epic hour, otherwise junk. Bajo: many decent hours.
    alto_frame = {"hourly": [
        _row("2026-09-01T12:00", wave_height=1.8, wave_period=14.0,
             wind_speed_10m=5.0, wind_direction_10m=0.0),
        *[_row(f"2026-09-0{d}T12:00", wave_height=0.1, wave_period=4.0,
               wind_speed_10m=80.0, wind_direction_10m=180.0) for d in (2, 3, 4, 5)],
    ]}
    bajo_frame = {"hourly": [
        _row(f"2026-09-0{d}T12:00", wave_height=1.8, wave_period=14.0,
             wind_speed_10m=5.0, wind_direction_10m=0.0) for d in (1, 2, 3, 4, 5)
    ]}
    ranked = rank_spots({("Alto", "R"): alto_frame, ("Bajo", "R"): bajo_frame}, [alto, bajo])
    assert ranked[0]["name"] == "Bajo"
    assert ranked[0]["surfable_hours"] > ranked[1]["surfable_hours"]
    assert "best_time" in ranked[0] and "best_hour" in ranked[0]


def test_rank_spots_skips_missing_forecasts():
    ranked = rank_spots({}, [_spot(name="Ghost", region="R")])
    assert ranked == []


def test_rank_spots_best_ignores_night():
    spot = _spot(name="Night Owl", region="R")
    # 23:00 is perfect and clean; midday is merely decent — the pick must
    # still be the daylight hour.
    frame = {
        "hourly": [
            _row("2026-09-01T23:00", wave_height=1.8, wave_period=14.0,
                 wind_speed_10m=5.0, wind_direction_10m=0.0),
            _row("2026-09-01T12:00", wave_height=1.0, wave_period=10.0,
                 wind_speed_10m=9.0, wind_direction_10m=0.0),
        ],
        "daily": {"time": ["2026-09-01"],
                  "sunrise": ["2026-09-01T06:00"], "sunset": ["2026-09-01T18:00"]},
    }
    (row,) = rank_spots({("Night Owl", "R"): frame}, [spot])
    assert row["best_time"] == "2026-09-01T12:00"
    assert row["total_hours"] == 2


# ---- Monotonicity properties ----

def test_bigger_swell_in_window_scores_ge(tmp_path=None):
    """Bigger swell inside the ideal window scores >= smaller swell."""
    spot = _spot()
    scores = [
        score_hour(h, 14.0, 5.0, 0.0, spot, wave_direction_deg=180.0, skill_level="advanced")["score"]
        for h in (0.8, 1.2, 1.6, 2.0)
    ]
    assert scores == sorted(scores)


def test_score_hour_rejects_bad_skill():
    with pytest.raises(ValueError):
        score_hour(1.5, 12.0, 5.0, 0.0, _spot(), skill_level="kook")


def test_rank_spots_this_week_alias():
    frame = _frame(["2026-09-01T12:00"])
    spot = _spot()
    key = (spot["name"], spot["region"])
    assert sc.rank_spots_this_week({key: frame}, [spot]) == rank_spots({key: frame}, [spot])
