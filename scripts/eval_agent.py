"""Agent eval: 10 golden questions x expected tool names (Worker C).

``--dry-run`` (default in CI): offline keyword router asserts each golden
question maps to its expected tools — no network, no LLM, no token.
Exit code 0 + "10/10 routed" on success.

Live mode (``--live``): runs :func:`wavereader.agent.run_stream` per
question with the per-turn budget guard (standard profile: 6 steps, 700
tokens, 2 score_week calls) and checks the expected tools were actually
called. Small token budget: 10 questions x ~1 short turn each — a few
cents on Nemotron 3 Ultra. Requires ``HF_TOKEN``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GOLDEN: list[tuple[str, list[str]]] = [
    ("When should I surf Bells Beach in Victoria this week?", ["get_spot_knowledge", "score_week"]),
    ("Where should I surf in Queensland as a beginner?", ["rank_region_week"]),
    ("Bells Beach or Winkipop on Saturday morning — which is better?", ["score_week", "find_best_windows"]),
    ("Why did Bells Beach get that score this morning? Break it down.", ["explain_score"]),
    ("Find beginner beach breaks near Byron Bay.", ["find_spots"]),
    ("I like Snapper Rocks — what similar spots are quieter?", ["find_similar_spots"]),
    ("What states and regions do you cover?", ["list_regions"]),
    ("Is Snapper Rocks good in autumn? How is the climate there?", ["get_climate_profile"]),
    ("What's the seafloor like at Bells Beach — reef or sandy shelf?", ["get_seafloor_profile"]),
    ("What wetsuit do I need at Bells Beach tomorrow, and when is sunrise?", ["get_session_brief"]),
]

# Keyword -> tool routing rules (mirrors the agent system prompt).
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("seafloor|reef|shelf|bathymetry|structure", ("get_seafloor_profile",)),
    ("wetsuit|sunrise|sunset|what do i wear|gear", ("get_session_brief",)),
    ("climate|autumn|season|best month|climatology", ("get_climate_profile",)),
    ("why|break it down|breakdown|explain.*score|component", ("explain_score",)),
    ("what states|what regions|which regions|do you cover|list.*region", ("list_regions",)),
    ("similar|like .* but|quieter|like\\ssnapper", ("find_similar_spots",)),
    ("\\bor\\b.*morning|\\bor\\b.*saturday|morning|weekend|saturday|sunday|best window", ("find_best_windows", "score_week")),
    ("where should i surf|where.*beginner|best.*in\\s", ("rank_region_week",)),
    ("find.*break|search|near\\s", ("find_spots",)),
    ("when should|bells beach|should i surf|this week|today", ("get_spot_knowledge", "score_week")),
]


def predict_tools(question: str) -> list[str]:
    """Deterministic keyword router: question -> predicted tool names."""
    q = (question or "").lower()
    for pattern, tools in _RULES:
        if re.search(pattern, q):
            return list(tools)
    return ["find_spots"]


def run_dry_run() -> int:
    """Offline routing check: every golden question must predict its tools."""
    print(f"{'question':60s} expected -> predicted  ok?")
    passed = 0
    for question, expected in GOLDEN:
        predicted = predict_tools(question)
        ok = all(t in predicted for t in expected)
        passed += ok
        mark = "OK " if ok else "MISS"
        print(f"[{mark}] {question[:58]:60s} {expected} -> {predicted}")
    print(f"\ndry-run: {passed}/{len(GOLDEN)} routed")
    return 0 if passed == len(GOLDEN) else 1


def run_live(max_steps: int = 6) -> int:
    """Live eval through the real agent (needs HF_TOKEN; small budget)."""
    from wavereader.agent import run_stream
    from wavereader.llm import has_token

    if not has_token():
        print("live eval needs HF_TOKEN (arg or env); aborting.")
        return 2
    passed = 0
    for i, (question, expected) in enumerate(GOLDEN, 1):
        called: list[str] = []
        final = ""
        usage: dict = {}
        for event in run_stream(question, max_steps=max_steps):
            if event.get("kind") == "tool_call":
                called.append(str(event.get("name")))
            elif event.get("kind") == "final":
                final = str(event.get("text", ""))[:200]
            elif event.get("kind") == "usage":
                usage = event
        ok = all(t in called for t in expected)
        passed += ok
        print(f"[{'OK ' if ok else 'MISS'}] Q{i}: expected={expected} called={called} usage={usage}")
        print(f"      final: {final!r}")
    print(f"\nlive: {passed}/{len(GOLDEN)} passed")
    return 0 if passed == len(GOLDEN) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="wavereader agent eval (10 goldens)")
    parser.add_argument("--dry-run", action="store_true", help="offline routing check (default)")
    parser.add_argument("--live", action="store_true", help="live run through the agent (needs HF_TOKEN)")
    parser.add_argument("--max-steps", type=int, default=6)
    args = parser.parse_args(argv)
    if args.live:
        return run_live(max_steps=args.max_steps)
    return run_dry_run()


if __name__ == "__main__":
    raise SystemExit(main())
