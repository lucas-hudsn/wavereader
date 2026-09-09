# AGENTS.md

Guidance for AI coding agents working in this repo. The active surface is
`app.py` + `ui/` + `wavereader/` + `data/` (the v2 rebuild). `legacy/`
holds the frozen v1 front end (`main.py` + `app/`) — don't extend it; it
survives only as the fallback layer in `ui/_compat.py`.

## What is live now

- `app.py` — v2 entrypoint: `build()` + `gr.api` tools +
  `demo.launch(css=APP_CSS, mcp_server=True)`. Run `uv run python app.py`.
- `ui/` — the front end: `app.py` (layout + wiring, ≤3 `gr.State`),
  `panels/{book,swell,agent}.py`, `charts/{score,swell,wind,seafloor,climate,map}.py`,
  `_compat.py` (backend access: v2 core → `legacy.app.*` → stubs),
  `theme.py` (`APP_CSS`, lo-fi Courier identity — don't restyle without asking).
- `wavereader/` — pure core, typed + tested, no Gradio imports:
  `breaks.py` (catalogue, memoized `load_breaks`), `openmeteo.py`
  (versioned/atomic disk cache, seaward grid-snap), `scoring.py` (deterministic
  0–10 engine — the LLM never owns numbers), `seafloor.py` (GEBCO world model),
  `climate.py` (ERA5 5-yr profiles + audit), `tools.py` (the typed tool
  functions shared by agent + MCP), `agent.py` (smolagents `ToolCallingAgent`,
  native tool calls, budget: 6 steps / 2 score_week / 700 tokens),
  `narrate.py` + `llm.py` (one InferenceClient factory:
  Nemotron 3.5 Lightning via fireworks-ai, `WR_*` env overrides).
- `scripts/warm_caches.py` — pre-fill forecast + seafloor caches (demo hot
  start). `scripts/build_climate.py` — climatology builder.
- `data/` — `australia-surf-breaks-enriched.json` (238 breaks),
  `surf-break-schema.json` (contract), `climate/*.json` (ERA5 profiles),
  `surf-break-example-bells.json` (prompt worked example).
- `documents/VIDEO_SCRIPT.md` — the GTC entry video shot list.

## Conventions that matter

- Staged spin-ups: `ui/panels/swell.py::fetch_forecast` is a **generator**
  that yields stage 1 (charts, ~ms) then stage 2 (seafloor world model from
  a parallel thread). Status lines name the engine + latency. Keep that
  pattern for anything slow.
- Charts: theme through `ui/charts/_style.py::style_fig`; weekend shading
  via `add_weekend_shading`. Seafloor display is bicubically smoothed
  (scipy) — smoothing is display-only; stats stay on the raw grid.
- MCP surface = exactly `score_week` / `rank_region_week` / `explain_score`
  (`gr.api` in `app.py`). All event listeners are registered with
  `api_name=False` — keep it that way.
- The LLM never owns numbers. Scores/forecasts/analysis stay deterministic;
  the model narrates and cites tools.

## Data contracts

- Required break fields: `name`, `state`, `region`, `location`,
  `skillLevel`, `breakType`, `peakType`, `idealSwell`, `idealWind`,
  `idealTide`. Optional: `description`, `id`, `bestSeason`, `hazards`,
  `crowdFactor`. Never invent enum values — check
  `data/surf-break-schema.json` first.
- Canonical `state`/`region` always come from the input list, never the
  model. `location.country` is `"Australia"`.
- New prompts must load schema + example from `data/` (don't paste copies).

## Rules for edits

1. Everything is tracked in this repo (no nested git — don't re-init one).
2. Never commit `.env`, `.venv/`, `__pycache__/`, `.DS_Store`, `.cache/`
   (all ignored).
3. Never read `.env` or print secrets/tokens. Use `.env.example` for var
   names; check presence with `printenv HF_TOKEN | wc -c` or
   `[ -n "$HF_TOKEN" ]` style checks that never echo the value.
4. Keep prompt files in `data/`; keep `app.py` free of embedded schema text.
5. Test cheaply: `uv run pytest -q` (offline fixtures) +
   `uv run python -c "import app"` for import health. Live LLM calls cost
   inference — dry-run the agent via the injected fake model
   (`tests/test_agent_dryrun.py`) before any live turn.
