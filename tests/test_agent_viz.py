"""Agent-panel guarantee: every answered turn lands a visualisation.

Offline: the agent stream is faked (typed v2 events, no LLM/token/network)
so each test drives ``ui.panels.agent.chat_fn`` through a turn whose tools
produce no scored hours, then asserts the panel still ends with a chart in
the ``agent_strip`` slot (``AGENT_KEYS`` index 6) and a 📊 line in the chat.
"""

from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ui import _compat as C  # noqa: E402
from ui import contracts  # noqa: E402
from ui.panels import agent as agent_panel  # noqa: E402
from wavereader import tools as _tools  # noqa: E402

AGENT_STRIP = contracts.AGENT_KEYS.index("agent_strip")
CHATBOT = contracts.AGENT_KEYS.index("chatbot")

_BELLS_ARGS = {"spot_name": "Bells Beach", "region": "Victoria"}


def _tool_events(name: str, args: dict, obs) -> list[tuple]:
    return [("tool_call", {"name": name, "arguments": args}),
            ("tool_result", {"name": name, "arguments": args,
                             "observation": obs, "summary": "ok",
                             "ms": 1.0, "preview": ""})]


def _run(monkeypatch, events: list[tuple], final: str, query: str):
    def stream(message, **kwargs):
        yield ("step", {"n": 1})
        yield from events
        yield ("final", final)
        yield ("usage", {"steps": 1, "profile": "standard"})
    monkeypatch.setattr(C, "agent_run_stream", stream)
    records = C.list_breaks()
    selected = C.find_break(records, "Bells Beach")
    assert selected is not None, "Bells Beach must resolve from the catalogue"
    return list(agent_panel.chat_fn(
        query, [], "intermediate", "", selected,
        agent_panel.fresh_store(), "standard", C.ALL, C.ALL, records))


def _last_emit(monkeypatch, obs, tool_name: str, args: dict,
               final: str = "**Best: Bells Beach @ Sat am — 6/10.**",
               query: str = "test question"):
    outs = _run(monkeypatch, _tool_events(tool_name, args, obs), final, query)
    return outs, outs[-1]


def test_climate_turn_charts_swell_rose(monkeypatch):
    obs = _tools.get_climate_profile(**_BELLS_ARGS)
    assert "error" not in obs
    _outs, last = _last_emit(monkeypatch, obs, "get_climate_profile", _BELLS_ARGS)
    fig = last[AGENT_STRIP]
    assert isinstance(fig, go.Figure)
    assert any(t.type == "barpolar" for t in fig.data)
    assert "📊" in last[CHATBOT][-1]["content"]


def test_seafloor_turn_charts_depth_map(monkeypatch):
    obs = _tools.get_seafloor_profile(**_BELLS_ARGS)
    assert "error" not in obs
    grid = {"lats": [-38.31, -38.30, -38.29], "lngs": [144.29, 144.30, 144.31],
            "elev": [-20.0, -12.0, -6.0, -14.0, -8.0, -4.0,
                     -10.0, -5.0, -1.0],
            "n": 3, "center": {"lat": -38.30, "lng": 144.30}}
    monkeypatch.setattr(C, "get_seafloor",
                        lambda br, radius_km=1.2: {"grid": grid, "analysis": "",
                                                   "stats": {}})
    _outs, last = _last_emit(monkeypatch, obs, "get_seafloor_profile", _BELLS_ARGS)
    fig = last[AGENT_STRIP]
    assert isinstance(fig, go.Figure)
    assert any(t.type == "heatmap" for t in fig.data)
    assert "📊" in last[CHATBOT][-1]["content"]


def test_rank_turn_charts_leaderboard(monkeypatch):
    obs = {"region": "Victoria", "skill": "intermediate", "count": 2,
           "spots": [
               {"name": "Bells Beach", "region": "Surf Coast",
                "best_score": 7.5, "best_time": "2026-09-12T06:00"},
               {"name": "Anglesea", "region": "Surf Coast",
                "best_score": 5.0, "best_time": "2026-09-12T07:00"},
           ]}
    _outs, last = _last_emit(monkeypatch, obs, "rank_region_week", {"region": "Victoria"})
    fig = last[AGENT_STRIP]
    assert isinstance(fig, go.Figure)
    assert any(getattr(t, "orientation", None) == "h" for t in fig.data)
    assert "📊" in last[CHATBOT][-1]["content"]


def test_similarity_turn_charts_comparison(monkeypatch):
    obs = [
        {"name": "Kirra", "region": "Gold Coast", "breakType": "Point break",
         "skillLevel": "intermediate", "peakType": "Right", "similarity": 8.5},
        {"name": "Lennox Head", "region": "Northern Rivers",
         "breakType": "Point break", "skillLevel": "intermediate",
         "peakType": "Right", "similarity": 7.5},
    ]
    _outs, last = _last_emit(monkeypatch, obs, "find_similar_spots",
                      {"spot_name": "Snapper Rocks"})
    fig = last[AGENT_STRIP]
    assert isinstance(fig, go.Figure)
    assert any(getattr(t, "orientation", None) == "h" for t in fig.data)
    assert "📊" in last[CHATBOT][-1]["content"]


def test_explain_turn_charts_component_split(monkeypatch):
    obs = _tools.explain_score(**_BELLS_ARGS)
    assert "error" not in obs and obs.get("components")
    _outs, last = _last_emit(monkeypatch, obs, "explain_score", _BELLS_ARGS)
    fig = last[AGENT_STRIP]
    assert isinstance(fig, go.Figure)
    assert any(t.type == "bar" and getattr(t, "orientation", None) is None
               for t in fig.data)  # vertical bars leave orientation=None
    assert "📊" in last[CHATBOT][-1]["content"]


def test_knowledge_only_turn_charts_viewed_spot(monkeypatch):
    # Nothing chartable in the tool payloads → the viewed spot's own
    # scored week (engine fetch stubbed) closes the guarantee.
    hours = [{"time": f"2026-09-09T{h:02d}:00", "score": 4.0 + h % 4,
              "wave_height_m": 1.2, "wave_period_s": 9.0,
              "wind_speed_kt": 7.0, "wind_direction_deg": 220,
              "daylight": True} for h in range(6, 18)]
    monkeypatch.setattr(
        C, "get_scored_week",
        lambda br, skill="intermediate", days=7: {"scored": hours,
                                                  "skill": skill})
    obs = _tools.get_spot_knowledge(**_BELLS_ARGS)
    assert "error" not in obs
    _outs, last = _last_emit(monkeypatch, obs, "get_spot_knowledge", _BELLS_ARGS)
    fig = last[AGENT_STRIP]
    assert isinstance(fig, go.Figure) and fig.data
    assert "Charted" in last[CHATBOT][-1]["content"]


def test_scored_turn_still_charts_strip_midway(monkeypatch):
    # When score_week runs, the week strip is charted mid-turn and the
    # fallback must not replace it with a second end-of-turn chart (so
    # the stubbed engine fetch below must never fire, and later emits
    # only gr.skip() the plot slot).
    hours = [{"time": f"2026-09-09T{h:02d}:00", "score": 5.0,
              "wave_height_m": 1.0, "wave_period_s": 8.0,
              "wind_speed_kt": 6.0, "wind_direction_deg": 200,
              "daylight": True} for h in range(6, 18)]
    obs = {"spot": {"name": "Bells Beach", "region": "Surf Coast"},
           "skill": "intermediate", "scored": hours,
           "daily": [], "best": hours[0], "stub": True}
    monkeypatch.setattr(C, "get_scored_week", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("fallback fetch must not run when hours were charted")))
    outs, last = _last_emit(monkeypatch, obs, "score_week", _BELLS_ARGS)
    strip = contracts.AGENT_KEYS.index("agent_strip")
    charted = [o[strip] for o in outs if isinstance(o[strip], go.Figure)]
    assert charted, "mid-turn week strip never rendered"
    assert not isinstance(last[strip], go.Figure) or charted[-1] is last[strip]


def _scored_obs(spot_name: str, region: str, score: float) -> dict:
    hours = [{"time": f"2026-09-09T{h:02d}:00", "score": score - (h % 3) * 0.5,
              "wave_height_m": 1.2, "wave_period_s": 9.0,
              "wind_speed_kt": 7.0, "wind_direction_deg": 220,
              "daylight": True} for h in range(6, 18)]
    return {"spot": {"name": spot_name, "region": region},
            "skill": "intermediate", "scored": hours,
            "daily": [], "best": hours[0], "stub": True}


def test_where_query_sweeps_region_when_agent_didnt_rank(monkeypatch):
    # A recommendation question the agent answered without a rank sweep
    # still closes on the recommended-scores leaderboard: the panel runs a
    # deterministic engine sweep of the region named in the question
    # (NSW -> New South Wales), never the viewed spot's unrelated week.
    sweep = {"region": "New South Wales", "skill": "intermediate", "count": 2,
             "spots": [
                 {"name": "Bondi Beach", "region": "Sydney",
                  "best_score": 6.5, "best_time": "2026-09-12T07:00"},
                 {"name": "Byron Bay", "region": "Northern Rivers",
                  "best_score": 5.5, "best_time": "2026-09-12T08:00"},
             ]}
    monkeypatch.setattr(C, "api_rank_region_week",
                        lambda region, skill="intermediate", limit=10: sweep)
    monkeypatch.setattr(C, "get_scored_week", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("viewed-spot fallback must not run when the sweep hits")))
    obs = _tools.get_spot_knowledge(**_BELLS_ARGS)
    assert "error" not in obs
    _outs, last = _last_emit(
        monkeypatch, obs, "get_spot_knowledge", _BELLS_ARGS,
        query="Where should I surf in NSW this weekend as a beginner?")
    fig = last[AGENT_STRIP]
    assert isinstance(fig, go.Figure)
    assert any(getattr(t, "orientation", None) == "h" for t in fig.data)
    assert "recommended breaks — New South Wales" in last[CHATBOT][-1]["content"]


def test_seafloor_query_prefers_depth_map_over_leaderboard(monkeypatch):
    # When the question asks about the seafloor, the depth map wins even
    # with a rank sweep payload on the table — the chart matches the
    # question, not the tool order.
    rank_obs = {"region": "Victoria", "skill": "intermediate", "count": 1,
                "spots": [{"name": "Bells Beach", "region": "Surf Coast",
                           "best_score": 7.5, "best_time": "2026-09-12T06:00"}]}
    seafloor_obs = _tools.get_seafloor_profile(**_BELLS_ARGS)
    assert "error" not in seafloor_obs
    grid = {"lats": [-38.31, -38.30, -38.29], "lngs": [144.29, 144.30, 144.31],
            "elev": [-20.0, -12.0, -6.0, -14.0, -8.0, -4.0,
                     -10.0, -5.0, -1.0],
            "n": 3, "center": {"lat": -38.30, "lng": 144.30}}
    monkeypatch.setattr(C, "get_seafloor",
                        lambda br, radius_km=1.2: {"grid": grid, "analysis": "",
                                                   "stats": {}})
    events = _tool_events("rank_region_week", {"region": "Victoria"}, rank_obs)
    events += _tool_events("get_seafloor_profile", _BELLS_ARGS, seafloor_obs)
    outs = _run(monkeypatch, events,
                "**Best: Bells Beach @ Sat am — 6/10.**",
                "What's the seafloor like at Bells Beach?")
    fig = outs[-1][AGENT_STRIP]
    assert isinstance(fig, go.Figure)
    assert any(t.type == "heatmap" for t in fig.data)
    assert not any(getattr(t, "orientation", None) == "h" for t in fig.data)


def test_compare_query_charts_multi_spot_scores(monkeypatch):
    # Two score_week calls in one turn -> the turn closes on the
    # side-by-side best-score compare, not just the last spot's strip.
    events = []
    for name, region, score in (("Bells Beach", "Victoria", 7.0),
                                ("Snapper Rocks", "Queensland", 5.0)):
        args = {"spot_name": name, "region": region}
        events += _tool_events("score_week", args,
                               _scored_obs(name, region, score))
    outs = _run(monkeypatch, events,
                "**Best: Bells Beach @ Sun am — 7/10.**",
                "Compare Bells Beach and Snapper Rocks this weekend.")
    last = outs[-1]
    fig = last[AGENT_STRIP]
    assert isinstance(fig, go.Figure)
    assert any(getattr(t, "orientation", None) == "h" for t in fig.data)
    assert "best-score compare (2 spots)" in last[CHATBOT][-1]["content"]
