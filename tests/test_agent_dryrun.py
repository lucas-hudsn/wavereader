"""Offline dry-run tests for Worker C (no network, no LLM, no token).

Covers: 9 tools importable + plausibly shaped offline, system-prompt token
budget, golden-question routing, score_week per-turn budget guard, llm
factory defaults, narrator marker/think stripping.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_agent  # noqa: E402
from wavereader import agent as agent_mod  # noqa: E402
from wavereader import llm as llm_mod  # noqa: E402
from wavereader import narrate as narrate_mod  # noqa: E402
from wavereader import tools as tools_mod  # noqa: E402

EXPECTED_TOOLS = [
    "get_spot_knowledge",
    "get_climate_profile",
    "score_week",
    "rank_region_week",
    "explain_score",
    "find_best_windows",
    "find_spots",
    "find_similar_spots",
    "list_regions",
]


def test_nine_tools_registered():
    assert tools_mod.TOOL_NAMES == EXPECTED_TOOLS
    assert len(tools_mod.TOOLS) == 9
    for t in tools_mod.TOOLS:
        assert t.description and t.inputs is not None and t.output_type in ("object", "array", "string")


def test_list_regions_offline_shape():
    out = tools_mod.list_regions()
    assert isinstance(out, dict) and "states" in out and "regions_by_state" in out


def test_find_spots_offline_shape():
    out = tools_mod.find_spots(query="Queensland", limit=3)
    assert isinstance(out, list) and len(out) <= 3


def test_spot_tools_offline_plausible_shapes():
    # Unknown spot -> typed error dicts (no network touched).
    assert "error" in tools_mod.get_spot_knowledge(spot_name="No Such Break XYZ")
    assert "error" in tools_mod.score_week(spot_name="No Such Break XYZ")
    assert "error" in tools_mod.explain_score(spot_name="No Such Break XYZ")
    assert "error" in tools_mod.get_climate_profile(spot_name="No Such Break XYZ")
    assert "error" in tools_mod.rank_region_week(region="")
    assert "error" in tools_mod.find_best_windows(spot_name="No Such Break XYZ")
    miss = tools_mod.find_similar_spots(spot_name="No Such Break XYZ")
    assert isinstance(miss, list) and miss and "error" in miss[0]


def test_known_spot_offline_shapes():
    if not tools_mod.list_regions().get("states"):
        return  # no dataset present; nothing to resolve against
    first_state = tools_mod.list_regions()["states"][0]
    spots = tools_mod.find_spots(query=first_state, limit=1)
    assert spots, "dataset should yield at least one spot"
    name = spots[0]["name"]
    region = spots[0].get("region") or first_state
    knowledge = tools_mod.get_spot_knowledge(spot_name=name, region=region)
    assert knowledge.get("name") == name
    scored = tools_mod.score_week(spot_name=name, region=region, skill="intermediate")
    assert isinstance(scored.get("scored"), list) and scored["scored"]
    assert scored.get("best") and scored.get("daily")
    explained = tools_mod.explain_score(spot_name=name, region=region)
    assert explained.get("score") is not None and "components" in explained
    windows = tools_mod.find_best_windows(spot_name=name, region=region, daypart="morning")
    assert isinstance(windows.get("windows"), list)
    climate = tools_mod.get_climate_profile(spot_name=name, region=region)
    assert "climate" in climate and "findings" in climate
    ranked = tools_mod.rank_region_week(region=first_state, limit=3)
    if "error" in ranked:
        pytest.skip(f"forecast backend offline: {ranked['error']}")
    assert isinstance(ranked.get("spots"), list)
    similar = tools_mod.find_similar_spots(spot_name=name, region=region, limit=2)
    assert isinstance(similar, list)


def test_system_prompt_token_budget():
    est = agent_mod.prompt_token_estimate(agent_mod.SYSTEM_PROMPT)
    assert est <= 1500, f"system prompt ~{est} tokens, budget is 1500"


def test_golden_routing_8_of_8():
    missed = []
    for question, expected in eval_agent.GOLDEN:
        predicted = eval_agent.predict_tools(question)
        if not all(t in predicted for t in expected):
            missed.append((question, expected, predicted))
    assert len(eval_agent.GOLDEN) == 8
    assert not missed, f"routing misses: {missed}"


def test_score_week_budget_guard():
    counter: dict = {}
    guarded = agent_mod._guarded_score_week(counter)
    kwargs = {"spot_name": "No Such Break XYZ", "region": None, "skill": None}
    guarded(**kwargs)
    guarded(**kwargs)
    third = guarded(**kwargs)
    assert counter["score_week"] == 2
    assert "error" in third and "Budget exceeded" in third["error"]


def test_llm_factory_defaults_no_token():
    env_backup = {k: os.environ.get(k) for k in ("WR_MODEL", "WR_PROVIDER", "WR_BASE_URL")}
    try:
        for k in ("WR_MODEL", "WR_PROVIDER", "WR_BASE_URL"):
            os.environ.pop(k, None)
        assert llm_mod.get_model_id() == llm_mod.DEFAULT_MODEL
        assert "Nemotron-3.5-Lightning" in llm_mod.get_model_id()
        assert llm_mod.get_provider() == "fireworks-ai"
        assert llm_mod.get_base_url() is None
        assert "Ultra" not in llm_mod.get_model_id() and "Qwen" not in llm_mod.get_model_id()
        os.environ["WR_MODEL"] = "custom/model"
        os.environ["WR_PROVIDER"] = "custom-provider"
        os.environ["WR_BASE_URL"] = "http://localhost:11434/v1"
        assert llm_mod.get_model_id() == "custom/model"
        assert llm_mod.get_provider() == "custom-provider"
        assert llm_mod.get_base_url() == "http://localhost:11434/v1"
        client = llm_mod.get_client(hf_token="dummy")
        assert client is not None
    finally:
        for k, v in env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_narrator_stripping():
    dirty = "<think>planning here</think>@@REPORT@@\n- Sat: fun.\n\n**Recommendation: Sat -- light winds.**\n@@END@@"
    clean = narrate_mod._clean_output(dirty)
    assert "<think>" not in clean and "@@REPORT@@" not in clean
    assert "Recommendation" in clean
    assert narrate_mod._clean_output("We need to produce bullets. Real text.") != ""
    prompt = narrate_mod.build_report_prompt({"name": "Bells"}, "intermediate", [], None, 1)
    assert "Bells" in prompt
    assert narrate_mod.narrate_day({"date": "2026-09-07", "score": 7}) .startswith("2026-09-07")


def test_agent_factory_builds_with_injected_model():
    from smolagents import InferenceClientModel

    calls: list[dict] = []

    class FakeModel(InferenceClientModel):
        def __init__(self):
            pass

    created = agent_mod.create_agent(model=FakeModel(), max_steps=6)
    assert created.max_steps == 6
    tool_names = sorted(t.name for t in created.tools.values()) if isinstance(created.tools, dict) else sorted(t.name for t in created.tools)
    # ToolCallingAgent adds its built-in final_answer tool; ours must all be present.
    assert all(t in tool_names for t in EXPECTED_TOOLS), tool_names
