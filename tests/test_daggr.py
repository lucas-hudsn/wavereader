"""Unit tests for wavereader.daggr_pipeline — Morning Surf Report DAG."""

from __future__ import annotations

from wavereader.daggr_pipeline import (
    build_pipeline,
    find_spots_fn,
    fetch_forecasts_fn,
    score_forecasts_fn,
    rank_spots_fn,
    format_report_fn,
    _narration_preprocess,
    _narration_postprocess,
)


def test_find_spots_fn():
    result = find_spots_fn("QLD", skill=None)
    assert "spots" in result
    assert "region" in result
    assert result["region"] == "QLD"
    assert len(result["spots"]) > 0


def test_find_spots_fn_all_sentinel_means_no_filter():
    """The UI's "all" skill sentinel must not be passed to the substring match."""
    unfiltered = find_spots_fn("QLD", skill=None)
    all_sentinel = find_spots_fn("QLD", skill="all")
    assert len(all_sentinel["spots"]) == len(unfiltered["spots"]) > 0
    assert all_sentinel["skill"] is None


def test_find_spots_fn_with_skill():
    result = find_spots_fn("QLD", skill="beginner")
    assert "spots" in result
    for spot in result["spots"]:
        assert "beginner" in spot["additional_details"]["skill_level"].lower()


def test_pipeline_string_keys_end_to_end(tmp_path, monkeypatch):
    """fetch → score → rank works with "{name}|{region}" string keys."""
    from wavereader import forecasts as forecasts_mod

    fake = {
        "hourly": [
            {
                "time": "2024-01-01T06:00",
                "wave_height": 1.5,
                "wave_period": 12,
                "wave_direction": 135,
                "wind_speed_10m": 8,
                "wind_direction_10m": 180,
            }
        ]
    }
    monkeypatch.setattr(forecasts_mod, "get_forecast", lambda lat, lng, days=7: fake)

    spots_found = find_spots_fn("QLD")["spots"][:3]
    fetched = fetch_forecasts_fn(spots_found)
    assert fetched["forecasts"]
    for key in fetched["forecasts"]:
        assert isinstance(key, str) and "|" in key

    scored = score_forecasts_fn(fetched["forecasts"], spots_found)
    assert set(scored["scored"]) == set(fetched["forecasts"])

    ranked = rank_spots_fn(scored["scored"], spots_found)
    assert len(ranked["ranked"]) == len(spots_found)
    assert ranked["ranked"][0]["best_score"] >= 0


def test_narration_preprocess_flat_prompt():
    inputs = {
        "ranked": [{"name": "A", "region": "QLD", "best_score": 8.0}],
        "region": "QLD",
    }
    result = _narration_preprocess(inputs)
    # daggr's text-generation path sends the first value as a plain prompt
    assert list(result.keys())[0] == "prompt"
    assert isinstance(result["prompt"], str)
    assert "QLD" in result["prompt"]


def test_narration_postprocess_handles_shapes():
    assert _narration_postprocess("plain text") == {"ai_report": "plain text"}
    assert _narration_postprocess([{"generated_text": "gen"}]) == {"ai_report": "gen"}
    assert _narration_postprocess(42) == {"ai_report": "42"}


def test_format_report_fn_empty():
    result = format_report_fn([], "NSW")
    assert "report" in result
    assert "No spots" in result["report"]


def test_format_report_fn_with_data():
    ranked = [
        {
            "name": "Test Spot",
            "region": "QLD",
            "best_score": 8.5,
            "best_time": "2024-01-01T12:00",
            "best_hour": {
                "time": "2024-01-01T12:00",
                "score": 8.5,
                "components": {"swell_size": 9.0, "swell_direction": 8.0, "wind": 8.5, "period": 8.5},
            },
        }
    ]
    result = format_report_fn(ranked, "QLD")
    assert "report" in result
    assert "Test Spot" in result["report"]
    assert "8.5" in result["report"]


def test_format_report_fn_missing_direction_shows_na():
    ranked = [
        {
            "name": "Test Spot",
            "region": "QLD",
            "best_score": 8.5,
            "best_time": "2024-01-01T12:00",
            "best_hour": {
                "time": "2024-01-01T12:00",
                "score": 8.5,
                "components": {"swell_size": 9.0, "swell_direction": None, "wind": 8.5, "period": 8.5},
            },
        }
    ]
    result = format_report_fn(ranked, "QLD")
    assert "n/a" in result["report"]


def test_build_pipeline():
    graph = build_pipeline()
    assert graph is not None
    entry = graph.get_entry_nodes()
    assert len(entry) == 1
    assert entry[0].name == "User Input"
    outputs = graph.get_output_nodes()
    assert "Narrate Report" in outputs
    assert "Format Report" in outputs
    order = graph.get_execution_order()
    assert order[0] == "User Input"
    assert order[-1] in ("Narrate Report", "Format Report")
