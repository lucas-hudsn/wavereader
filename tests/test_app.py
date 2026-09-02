"""Unit tests for wavereader.app — Gradio UI chart functions and helpers."""

from __future__ import annotations

import json

from wavereader.app import (
    create_australia_map,
    create_seaborn_template,
    create_wave_height_chart,
    create_score_chart,
    create_ranking_chart,
    update_trace_panel,
    build_ui,
)


def test_australia_map_creates_figure():
    fig = create_australia_map()
    assert fig is not None
    assert len(fig.data) >= 1


def test_seaborn_template_has_keys():
    t = create_seaborn_template()
    assert "layout" in t
    assert "font" in t["layout"]
    assert "paper_bgcolor" in t["layout"]


def test_wave_height_chart_empty():
    fig = create_wave_height_chart({}, "Spot")
    assert fig is not None


def test_wave_height_chart_with_data():
    forecast = {
        "hourly": [
            {
                "time": f"2024-01-01T{i:02d}:00",
                "wave_height": 1.5,
                "wave_period": 10,
                "wind_speed_10m": 15,
                "wind_direction_10m": 135,
            }
            for i in range(24)
        ]
    }
    fig = create_wave_height_chart(forecast, "Snapper Rocks")
    assert len(fig.data) == 3  # wave height, period, wind


def test_score_chart_empty():
    fig = create_score_chart([], "Spot")
    assert fig is not None


def test_score_chart_with_data():
    scores = [
        {
            "time": f"2024-01-01T{i:02d}:00",
            "score": 7.5,
            "components": {
                "swell_size": 8.0,
                "swell_direction": 7.0,
                "wind": 7.5,
                "period": 7.5,
            },
        }
        for i in range(24)
    ]
    fig = create_score_chart(scores, "Snapper Rocks")
    assert len(fig.data) == 5  # total + 4 components


def test_ranking_chart_empty():
    fig = create_ranking_chart([], "NSW")
    assert fig is not None


def test_ranking_chart_with_data():
    ranked = [
        {"name": "A", "region": "NSW", "best_score": 8.5, "best_time": "2024-01-01T12:00"},
        {"name": "B", "region": "NSW", "best_score": 6.0, "best_time": "2024-01-01T08:00"},
    ]
    fig = create_ranking_chart(ranked, "NSW")
    assert len(fig.data) >= 1


def test_update_trace_panel_empty():
    result = update_trace_panel("")
    assert "No trace yet" in result


def test_update_trace_panel_with_data():
    trace = {
        "question": "Best spot?",
        "model": "Qwen",
        "provider": "hf",
        "events": [
            {"type": "tool_call", "data": {"name": "score_week", "arguments": {"spot_name": "A"}}},
            {"type": "tool_result", "data": {"observation": "[{score: 8.5}]"}},
        ],
    }
    result = update_trace_panel(json.dumps(trace))
    assert "Best spot?" in result
    assert "score_week" in result


def test_update_trace_panel_invalid_json():
    result = update_trace_panel("not json")
    assert result == "not json"


def test_build_ui_creates_blocks():
    demo = build_ui()
    assert demo is not None
