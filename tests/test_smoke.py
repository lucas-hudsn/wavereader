"""Smoke tests: package imports and pyproject sanity (structure milestone)."""

import tomllib
from pathlib import Path

import wavereader
from wavereader import agent, api, app, daggr_pipeline, forecasts, scoring, spots, tools

REPO = Path(__file__).resolve().parent.parent


def test_version():
    assert wavereader.__version__ == "0.1.0"


def test_all_modules_importable():
    for mod in (agent, api, app, daggr_pipeline, forecasts, scoring, spots, tools):
        assert mod.__doc__


def test_pyproject_pinned():
    cfg = tomllib.loads((REPO / "pyproject.toml").read_text())
    assert cfg["project"]["requires-python"] == ">=3.12"
    deps = " ".join(cfg["project"]["dependencies"])
    assert "langchain" not in deps
    assert "anthropic" not in deps
    for required in ("gradio", "daggr", "openai", "httpx", "pydantic"):
        assert required in deps


def test_api_app_exists():
    routes = {r.path for r in api.app.routes}
    assert {"/", "/spots", "/forecast", "/score"} <= routes


def test_golden_questions_eval_dry_run():
    from evals.run_evals import load_golden_questions, run_single_eval
    questions = load_golden_questions()
    assert len(questions) == 10
    for q in questions:
        res = run_single_eval(q, None, is_dry_run=True)
        assert res["passed"] is True
