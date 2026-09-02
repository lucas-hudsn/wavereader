"""Fixed "Morning Surf Report" DAG visualised with daggr.

Daggr is beta and has NO conditional branching: this visualises the fixed
morning pipeline only, never the dynamic chat agent loop.

Pipeline:
  InputNode(region, skill) → FindSpotsFn → FetchForecastsFn →
  ScoreForecastsFn → RankSpotsFn → { FormatReportFn (deterministic),
  InferenceNode (narrates) }

Forecasts/scores flow between nodes keyed by ``"{name}|{region}"`` strings
(tuple keys don't survive a round-trip through gr.JSON).
"""

from __future__ import annotations

import json
from typing import Any

import gradio as gr
from daggr import Graph, FnNode, InputNode, InferenceNode

from wavereader import forecasts, scoring, spots

NARRATION_PROMPT = (
    "You are a surf forecaster. Given a ranked list of spots with scores, "
    "write a concise, enthusiastic morning surf report. Keep it under 200 "
    "words. Include specific times and scores. Be practical and actionable."
)


def _spot_key(spot: dict) -> str:
    return f"{spot['name']}|{spot['region']}"


def _split_key(key: str) -> tuple[str, str]:
    name, region = key.split("|", 1)
    return name, region


def find_spots_fn(region: str, skill: str | None = None) -> dict[str, Any]:
    """Find breaks in a region with optional skill filter.

    The UI's "all" sentinel means no filter — ``spots.find_spots`` does a
    substring skill match, so "all" must become None.
    """
    if skill in (None, "", "all"):
        skill = None
    breaks = spots.find_spots(region=region, skill=skill, limit=20)
    return {
        "spots": [b.model_dump() for b in breaks],
        "region": region,
        "skill": skill,
    }


def _find_spots_node_fn(region: str, skill: str | None = None):
    """daggr adapter: FnNode maps tuple returns to output ports in order.

    ``find_spots_fn`` returns a dict for direct/test use; daggr's executor
    treats a dict return as a single value for the first port only, so the
    node unwraps it into ``(spots, region, skill)``.
    """
    result = find_spots_fn(region, skill)
    return result["spots"], result["region"], result["skill"]


def fetch_forecasts_fn(spots_list: list[dict]) -> dict[str, Any]:
    """Fetch forecasts for all spots."""
    forecasts_map = {}
    for spot in spots_list:
        fc = forecasts.get_forecast(
            spot["coordinates"]["lat"], spot["coordinates"]["lng"], days=7
        )
        forecasts_map[_spot_key(spot)] = fc
    return {"forecasts": forecasts_map}


def score_forecasts_fn(forecasts_map: dict, spots_list: list[dict]) -> dict[str, Any]:
    """Score forecasts for all spots."""
    scored = {}
    for spot in spots_list:
        key = _spot_key(spot)
        if key in forecasts_map:
            scored[key] = scoring.score_week(forecasts_map[key], spot)
    return {"scored": scored}


def rank_spots_fn(scored: dict, spots_list: list[dict]) -> dict[str, Any]:
    """Rank spots by best score from the already-scored hourly rows.

    Scores were computed in the previous node keyed by ``"{name}|{region}"``
    strings (tuple keys don't survive a round-trip through gr.JSON), so rank
    directly here rather than re-entering ``scoring.rank_spots_this_week``.
    """
    ranked = []
    for spot in spots_list:
        key = _spot_key(spot)
        hours = scored.get(key) or []
        best_hour = max(hours, key=lambda h: h["score"]) if hours else None
        ranked.append(
            {
                "name": spot["name"],
                "region": spot["region"],
                "best_score": best_hour["score"] if best_hour else 0.0,
                "best_time": best_hour["time"] if best_hour else None,
                "best_hour": best_hour,
            }
        )
    ranked.sort(key=lambda x: x["best_score"], reverse=True)
    return {"ranked": ranked}


def format_report_fn(ranked: list[dict], region: str) -> dict[str, str]:
    """Format the deterministic morning surf report (authoritative output)."""
    if not ranked:
        return {"report": f"No spots found in {region}."}

    lines = [f"☀️ **Morning Surf Report — {region}**", ""]
    lines.append("📅 Top picks for this week:")
    lines.append("")

    for i, spot in enumerate(ranked[:5], 1):
        best = spot["best_hour"]
        time_str = best["time"].split("T")[1][:5] if best and best.get("time") else "N/A"
        score = best["score"] if best else 0
        comps = best["components"] if best else {}

        emoji = "🟢" if score >= 7 else "🟡" if score >= 5 else "🔴"
        lines.append(f"{i}. {emoji} **{spot['name']}** — Score: {score:.1f}/10 @ {time_str}")
        lines.append(
            f"   Swell: {comps.get('swell_size') or 0:.1f} | "
            f"Dir: {comps.get('swell_direction') if comps.get('swell_direction') is not None else 'n/a'} | "
            f"Wind: {comps.get('wind') or 0:.1f} | Period: {comps.get('period') or 0:.1f}"
        )

    lines.append("")
    lines.append("💡 *Scores are deterministic (0-10) based on ideal swell/wind/period for each break.*")
    lines.append("*Tide is qualitative only — check local tide charts.*")

    return {"report": "\n".join(lines)}


def _narration_preprocess(inputs: dict) -> dict[str, str]:
    """Flatten ranked spots into a single text-generation prompt.

    daggr's text-generation path calls ``client.text_generation(prompt)``
    with the first input value — an OpenAI chat payload would be dumped in
    as a list of dicts, so keep it a plain string.
    """
    prompt = (
        f"{NARRATION_PROMPT}\n\n"
        f"Region: {inputs['region']}\n"
        f"Ranked spots: {json.dumps(inputs['ranked'][:5], default=str)}\n\n"
        "Write a morning surf report."
    )
    return {"prompt": prompt}


def _narration_postprocess(result: Any) -> dict[str, str]:
    """Extract text from a text_generation result (str or list of dicts)."""
    if isinstance(result, str):
        text = result
    elif isinstance(result, list) and result and isinstance(result[0], dict):
        text = result[0].get("generated_text", str(result))
    else:
        text = str(result)
    return {"ai_report": text}


def build_pipeline() -> Graph:
    """Assemble the fixed morning-report DAG."""
    input_node = InputNode(
        name="User Input",
        ports={
            "region": gr.Dropdown(
                choices=["NSW", "QLD", "VIC", "WA", "SA", "TAS"],
                label="Region",
                value="NSW",
            ),
            "skill": gr.Dropdown(
                choices=["beginner", "intermediate", "advanced", "expert", "all"],
                label="Skill Level",
                value="all",
            ),
        },
    )

    find_spots_node = FnNode(
        _find_spots_node_fn,
        name="Find Spots",
        inputs={
            "region": input_node.region,
            "skill": input_node.skill,
        },
        outputs={"spots": gr.JSON(), "region": gr.Textbox(), "skill": gr.Textbox()},
    )

    fetch_forecasts_node = FnNode(
        fetch_forecasts_fn,
        name="Fetch Forecasts",
        inputs={"spots_list": find_spots_node.spots},
        outputs={"forecasts": gr.JSON()},
    )

    score_forecasts_node = FnNode(
        score_forecasts_fn,
        name="Score Forecasts",
        inputs={
            "forecasts_map": fetch_forecasts_node.forecasts,
            "spots_list": find_spots_node.spots,
        },
        outputs={"scored": gr.JSON()},
    )

    rank_spots_node = FnNode(
        rank_spots_fn,
        name="Rank Spots",
        inputs={
            "scored": score_forecasts_node.scored,
            "spots_list": find_spots_node.spots,
        },
        outputs={"ranked": gr.JSON()},
    )

    # Narrate with the LLM — narration only; scores stay deterministic.
    narrate_node = InferenceNode(
        model="Qwen/Qwen3-Next-80B-A3B-Instruct",
        name="Narrate Report",
        inputs={
            "ranked": rank_spots_node.ranked,
            "region": find_spots_node.region,
        },
        outputs={"ai_report": gr.Markdown()},
        preprocess=_narration_preprocess,
        postprocess=_narration_postprocess,
    )

    format_report_node = FnNode(
        format_report_fn,
        name="Format Report",
        inputs={
            "ranked": rank_spots_node.ranked,
            "region": find_spots_node.region,
        },
        outputs={"report": gr.Markdown()},
    )

    graph = Graph("Morning Surf Report", nodes=[input_node])
    for node in (
        find_spots_node,
        fetch_forecasts_node,
        score_forecasts_node,
        rank_spots_node,
        narrate_node,
        format_report_node,
    ):
        graph.add(node)

    return graph


if __name__ == "__main__":
    graph = build_pipeline()
    graph.launch(host="0.0.0.0", port=7861)
