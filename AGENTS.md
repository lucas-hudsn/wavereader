# AGENTS.md

Guidance for AI coding agents (and humans) working in this repo.

## Project context

**wavereader** is an agentic surf forecaster for Australian breaks. It is being
built as an entry for the NVIDIA GTC Berlin Golden Ticket contest
(#NVIDIAGTC). **Hard deadline: a demo video is recorded by Monday Sep 7, 2026**
(contest submissions close Sep 10). When making trade-offs, optimise for "does
this make the Sep 7 demo better" over completeness or elegance.

The product promises (see README.md):

1. Agent answers "which days are good near X / what time should I surf Y".
2. Forecast data the agent surfaces is rendered as **interactive graphs**
   (seaborn-styled: hourly wave height, period, wind speed/direction).
3. **Home page is a map of Australia** where the user selects their break.
4. Reasoning is visible: agent trace panel + daggr "Morning Surf Report" canvas.
5. Model hosting switchable between Hugging Face Inference and NVIDIA NIM.

## Stack rules (decided — do not relitigate)

- **Python 3.12** (pin in `.python-version`). `pyproject.toml` currently says
  `>=3.14` — downgrade it; 3.14 has unnecessary lib-compatibility risk for a
  one-week build.
- **Package manager:** uv (`uv add ...`, `uv sync`).
- **Agent framework:** smolagents (CodeAgent). The tool loop uses smolagents'
  CodeAgent with InferenceClientModel for Hugging Face / NVIDIA NIM. Remove
  `langchain-community` from deps when touched. `ddgs` stays (used by
  `data/generate_data.py`).
- **Provider-agnostic LLM client:** one OpenAI-compatible client class; the
  base URL + key come from env vars (`HF_TOKEN`, `NVIDIA_API_KEY`). Default
  model: `Qwen/Qwen3-Next-80B-A3B-Instruct` — chosen because it is the only
  tested model supporting *both* OpenAI-style tool calling and strict
  `json_schema` response format on the HF router (see
  `data/GENERATION.md` before swapping models).
- **The LLM never owns numbers.** Forecasts, scores and rankings come from
  `scoring.py` and `forecasts.py` (deterministic). The agent interprets and
  explains. Never let the model compute a "surf score" itself.
- **Charts:** interactive, seaborn-styled, rendered whenever the agent
  surfaces forecast/wind data in the UI. Prefer plotly/altair with seaborn
  aesthetics if pure seaborn (static) can't be interactive in Gradio.
- **Backend:** FastAPI (`wavereader/api.py`) owns data endpoints
  (`/spots`, `/forecast`, `/score`, `/ask`); Gradio (`wavereader/app.py`) is
  the demo UI and calls the core modules. No htmx/custom frontend this week.

## Target layout

```
wavereader/
  spots.py          # load + validate + search breaks (name/city/region/skill)
  forecasts.py      # Open-Meteo Marine + weather client; hourly, 7-day; disk cache
  scoring.py        # deterministic 0–10 surf-quality score/hour + component breakdown
  agent.py          # smolagents CodeAgent; streaming; trace capture; HF⇄NIM switch
  tools.py          # get_forecast, score_week, find_spots, get_spot_knowledge,
                    # rank_spots_this_week
  api.py            # FastAPI endpoints
  app.py            # Gradio UI: Australia map home page, chat, charts, trace panel
  daggr_pipeline.py # fixed "Morning Surf Report" DAG (see ROADMAP.md caveat)
data/
  breaks.json       # input: 100 breaks (name + region)
  break_details.json# output: structured per-break profiles (schema in GENERATION.md)
  generate_data.py  # LLM dataset generator (done — do not rewrite)
  GENERATION.md     # why the generator is built this way — read before touching it
evals/
  golden_questions.json  # ~10 questions + expected behaviors; run before recording
```

## Conventions

- `data/break_details.json` is the source of truth for spot knowledge. Add a
  validation pass (`spots.py`) rather than hand-editing records: check coords
  are plausible for the named region and ranges are sane; spot-check ~10
  against real local knowledge.
- Records are keyed by `(name, region)`; keep identity fields anchored to the
  input (the generator already overwrites model renames — preserve that).
- Tide is **qualitative only** (from the knowledge base); Open-Meteo has no
  tides. Don't promise tide curves.
- Open-Meteo wave grid points sit offshore: fetch slightly seaward of a
  spot's coords and keep the offset consistent.
- Cache forecast responses to disk; the demo must survive API flakiness and
  rate limits.
- Daggr is beta, **no conditional branching** — it visualises the fixed
  Morning Surf Report pipeline only, never the dynamic chat agent loop.
- `main.py` is a leftover hello-world FastAPI scaffold; fold it into
  `wavereader/api.py` when the real API lands, don't build on it.
- Every milestone should leave the repo in a state where `uv sync && uv run
  pytest` passes (unit tests focus on `scoring.py` and `spots.py`).

## Evals

`evals/golden_questions.json` is the pre-recording gate: ~10 real questions
(e.g. near-me weekly ranking with skill filter, best-hours-today, spot Q&A)
with expected behaviors. Run it against the deployed app before recording the
video; a failing eval blocks the recording, not the other way round.
