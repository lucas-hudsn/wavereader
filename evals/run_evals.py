"""Automated evaluation runner for WaveReader golden questions.

Pre-recording gate for the Sep 7 demo video. Evaluates the 10 golden questions
from ``evals/golden_questions.json`` against the live SurfAgent (or mock mode
in offline CI/dry-runs).

Usage:
    uv run python evals/run_evals.py
    uv run python evals/run_evals.py --provider nim
    uv run python evals/run_evals.py --question-id gq-04
    uv run python evals/run_evals.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from wavereader.agent import PROVIDER_HF, PROVIDER_NIM, SurfAgent, _detect_provider

EVALS_DIR = Path(__file__).resolve().parent
GOLDEN_QUESTIONS_FILE = EVALS_DIR / "golden_questions.json"

# Expected tool patterns for golden questions
QUESTION_EXPECTED_TOOLS: dict[str, list[str]] = {
    "gq-01": ["find_spots", "rank_spots_this_week"],
    "gq-02": ["find_spots", "rank_spots_this_week"],
    "gq-03": ["get_forecast", "score_week"],
    "gq-04": ["get_spot_knowledge"],
    "gq-05": ["find_spots", "rank_spots_this_week", "score_week"],
    "gq-06": ["get_forecast", "get_spot_knowledge"],
    "gq-07": ["score_week", "get_spot_knowledge", "get_forecast"],
    "gq-08": ["get_forecast"],
    "gq-09": ["find_spots", "rank_spots_this_week", "get_spot_knowledge"],
    "gq-10": ["score_week", "get_forecast", "get_spot_knowledge"],
}


def load_golden_questions() -> list[dict[str, Any]]:
    with open(GOLDEN_QUESTIONS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("questions", [])


def run_single_eval(
    question_data: dict[str, Any],
    agent: SurfAgent,
    is_dry_run: bool = False,
) -> dict[str, Any]:
    qid = question_data["id"]
    q_text = question_data["question"]
    start_time = time.time()

    if is_dry_run:
        # Mock run simulating successful tool calls
        expected = QUESTION_EXPECTED_TOOLS.get(qid, ["find_spots"])
        tool_calls = [expected[0]]
        answer = f"Dry-run answer for {qid} referencing {tool_calls[0]}."
        duration = 0.05
        passed = True
        notes = "Dry-run simulation"
        return {
            "id": qid,
            "question": q_text,
            "passed": passed,
            "duration": duration,
            "steps": len(tool_calls) + 1,
            "tools_called": tool_calls,
            "notes": notes,
            "answer": answer,
        }

    try:
        answer = agent.run(q_text)
        duration = time.time() - start_time
        trace = agent.trace

        tool_calls = []
        if trace:
            for event in trace.events:
                if event.type == "tool_call":
                    tool_name = event.data.get("name") or event.data.get("tool")
                    if tool_name:
                        tool_calls.append(tool_name)

        # Check assertions
        passed = True
        reasons = []

        if not answer or answer.strip() == "*(empty answer)*":
            passed = False
            reasons.append("Empty answer")

        expected_tools = QUESTION_EXPECTED_TOOLS.get(qid, [])
        # Pass if at least one of the expected tools was called
        if expected_tools and not any(t in tool_calls for t in expected_tools):
            passed = False
            reasons.append(f"Missing expected tools (called: {tool_calls}, expected: {expected_tools})")

        notes = "OK" if passed else "; ".join(reasons)

        return {
            "id": qid,
            "question": q_text,
            "passed": passed,
            "duration": duration,
            "steps": len(tool_calls) + 1,
            "tools_called": tool_calls,
            "notes": notes,
            "answer": answer,
        }
    except Exception as exc:
        duration = time.time() - start_time
        return {
            "id": qid,
            "question": q_text,
            "passed": False,
            "duration": duration,
            "steps": 0,
            "tools_called": [],
            "notes": f"Error: {exc}",
            "answer": "",
        }


def format_scorecard(results: list[dict[str, Any]]) -> str:
    lines = [
        "",
        "# WaveReader Golden Questions Evaluation Scorecard",
        "",
        "| ID | Question | Status | Duration | Steps | Tools Called | Notes |",
        "|---|---|:---:|:---:|:---:|---|---|",
    ]
    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        q_short = r["question"] if len(r["question"]) <= 45 else r["question"][:42] + "..."
        tools = ", ".join(r["tools_called"]) if r["tools_called"] else "–"
        lines.append(
            f"| {r['id']} | {q_short} | {status} | {r['duration']:.2f}s | {r['steps']} | `{tools}` | {r['notes']} |"
        )

    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    pass_rate = (passed_count / total_count * 100) if total_count else 0.0

    lines.extend([
        "",
        f"**Summary:** {passed_count}/{total_count} passed ({pass_rate:.1f}%)",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run WaveReader golden questions evals.")
    parser.add_argument("--provider", choices=[PROVIDER_HF, PROVIDER_NIM], help="LLM provider")
    parser.add_argument("--model", help="Model override")
    parser.add_argument("--question-id", help="Run only specific question ID (e.g., gq-01)")
    parser.add_argument("--dry-run", action="store_true", help="Run in mock/dry-run mode without network")
    parser.add_argument("--output", help="Save markdown report to file")
    args = parser.parse_args()

    questions = load_golden_questions()
    if args.question_id:
        questions = [q for q in questions if q["id"] == args.question_id]
        if not questions:
            print(f"Error: Question ID '{args.question_id}' not found.")
            return 1

    print(f"Running evals for {len(questions)} questions (dry_run={args.dry_run})...")

    agent = None
    if not args.dry_run:
        try:
            agent = SurfAgent(provider=args.provider, model=args.model)
            print(f"Initialized SurfAgent with provider='{agent.provider}', model='{agent.model}'")
        except Exception as exc:
            print(f"Error initializing SurfAgent: {exc}")
            print("Run with --dry-run to test eval harness without API keys.")
            return 1

    results = []
    for q in questions:
        print(f"  Evaluating {q['id']}... ", end="", flush=True)
        res = run_single_eval(q, agent, is_dry_run=args.dry_run)
        print("PASS" if res["passed"] else "FAIL")
        results.append(res)

    scorecard = format_scorecard(results)
    print(scorecard)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(scorecard, encoding="utf-8")
        print(f"Scorecard saved to {out_path}")

    all_passed = all(r["passed"] for r in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
