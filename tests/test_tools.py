"""Direct wiring tests for wavereader.tools — with forecasts mocked, spots real."""

from __future__ import annotations

from unittest.mock import patch

from wavereader import tools


def _fake_forecast(lat, lng, days=7):
    return {
        "hourly": [
            {
                "time": f"2024-01-01T{h:02d}:00",
                "wave_height": 1.5,
                "wave_period": 11,
                "wave_direction": 135,
                "wind_speed_10m": 9,
                "wind_direction_10m": 180,
            }
            for h in range(6)
        ]
    }


def test_get_forecast_known_spot():
    with patch("wavereader.forecasts.get_forecast", side_effect=_fake_forecast) as mock_fc:
        result = tools.get_forecast("Snapper Rocks", "QLD")
    assert "hourly" in result
    mock_fc.assert_called_once()


def test_get_forecast_unknown_spot():
    result = tools.get_forecast("Nowhere", "XX")
    assert "error" in result


def test_score_week_known_spot():
    with patch("wavereader.forecasts.get_forecast", side_effect=_fake_forecast):
        result = tools.score_week("Snapper Rocks", "QLD")
    assert isinstance(result, list)
    assert len(result) == 6
    assert "score" in result[0]


def test_score_week_unknown_spot_returns_error_dict():
    """Bad spot name must be distinguishable from no scoreable hours."""
    result = tools.score_week("Nowhere", "XX")
    assert isinstance(result, dict)
    assert "error" in result


def test_find_spots_by_query():
    results = tools.find_spots(query="Snapper")
    assert any(r["name"] == "Snapper Rocks" for r in results)


def test_find_spots_by_skill():
    results = tools.find_spots(query="Bells", skill="advanced")
    for r in results:
        assert "advanced" in r["additional_details"]["skill_level"].lower()


def test_get_spot_knowledge():
    result = tools.get_spot_knowledge("Bells Beach", "VIC")
    assert result["name"] == "Bells Beach"
    assert "ideal_swell" in result


def test_get_spot_knowledge_unknown():
    assert "error" in tools.get_spot_knowledge("Nowhere", "XX")


def test_rank_spots_this_week_ranks_descending():
    with patch("wavereader.forecasts.get_forecast", side_effect=_fake_forecast):
        ranked = tools.rank_spots_this_week("TAS", skill=None)
    assert ranked, "expected at least one TAS break"
    scores = [r["best_score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)
    for r in ranked:
        assert r["region"] == "TAS"
        assert r["best_time"]


def test_normalize_skill():
    assert tools._normalize_skill(None) == "intermediate"
    assert tools._normalize_skill("beginner") == "beginner"
    assert tools._normalize_skill("Beginner Surfer") == "beginner"
    assert tools._normalize_skill("adv") == "advanced"
    assert tools._normalize_skill("expert only") == "expert"
    assert tools._normalize_skill("pro") == "expert"
    assert tools._normalize_skill("something else") == "intermediate"


def test_score_week_forwards_skill():
    with patch("wavereader.forecasts.get_forecast", side_effect=_fake_forecast):
        res_beg = tools.score_week("Snapper Rocks", "QLD", skill="beginner")
        res_exp = tools.score_week("Snapper Rocks", "QLD", skill="expert")
    assert isinstance(res_beg, list) and isinstance(res_exp, list)
    assert res_beg[0]["skill_level"] == "beginner"
    assert res_exp[0]["skill_level"] == "expert"


def test_rank_spots_this_week_forwards_skill():
    with patch("wavereader.forecasts.get_forecast", side_effect=_fake_forecast):
        ranked = tools.rank_spots_this_week("QLD", skill="beginner")
    assert ranked
    assert all(r["skill_level"] == "beginner" for r in ranked)
