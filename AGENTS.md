# AGENTS.md

Guidance for AI coding agents working in this repo. The active surface is
`main.py` + `app/` + `data/`. `wavereader/` was deleted after its port
to `app/agent.py` + `app/agent_tools.py`.

## What is live now

- `main.py` — Gradio map front end. Run with `uv run python main.py`.
- `app/generate_surf_break.py` — single-shot structured-JSON generator.
- `app/generate_base_data.py` — batch/resumable enrichment runner.
- `data/` — `australia-surf-breaks.json` (input list),
  `australia-surf-breaks-enriched.json` (generated output),
  `surf-break-schema.json` (conformance contract),
  `surf-break-example-bells.json` (prompt worked example).

## Front-end modules (`main.py` + `app/` UI layer)

Entry: `main.py` (thin: re-exports + `main()` → `demo.launch(css=APP_CSS)`)
calls `app/ui.py::build_demo()`. Run with `uv run python main.py`.

- `app/config.py` — paths (`DATA_PATH`), `ALL`, `SKILL_ORDER`/`SKILL_COLORS`,
  `AUSTRALIA_CENTER`/`ZOOM`, shared strings (`SCORE_EXPLAINER_MD`,
  `BROWSE_INTRO`, `AGENT_INTRO`, ...). `app/theme.py` — `APP_CSS` only.
- `app/breaks_data.py` — `load_breaks()` reads
  `data/australia-surf-breaks-enriched.json` into `DF` (handles legacy
  `{"name | state | region": {...}}` dict format too, drops `error` rows).
  Derives `STATES`, `REGIONS_BY_STATE`, `ALL_REGIONS`, `SKILLS`.
  `filter_breaks(df, state, region, skill)` — `"All"`/None = no filter,
  case-insensitive on canonical `state` / `region` / `skillLevel`.
- `app/maps.py` — `build_map(records, default_view)` (Plotly `Scattermap`,
  `open-street-map` style, marker colour by `SKILL_COLORS`, point order ==
  records order). Auto-centers/zooms via `_zoom_for_span()` unless
  `default_view` (unfiltered → whole Australia). `build_map_with_custom()`
  adds the gold star marker for the session break. `_lat()` / `_lng()`
  return None on missing coords.
- `app/break_details.py` — `break_to_table(break_)` flattens one record to a
  Field/Value dataframe; `_join()` stringifies list fields; `_cam_*` wrappers
  + `CAMS` overlay via direct `from app import surf_cams` (optional, never
  breaks the UI).
- `app/browse_sync.py` — `update_map`, `on_break_pick`, region-choice
  helpers, `mirror_*` one-way filter↔prefs sync, `resync_on_mode_toggle`,
  `_format_pref_chip`. `_resolve_pick()` maps a break-list label back to its
  record (custom break carries a `⭐ (your break)` suffix).
- `app/custom_break.py` — `generate_custom_break()` streams
  `(telemetry, details, map, dropdown, state)` tuples via `yield` (lazy
  `from app import generate_surf_break`, no `importlib` shims). Empty custom
  state/region fields fall back to the main map filters; explicit values win.
  Exactly one custom break per session (`gr.State`, never written to disk).
  `clear_custom_break()` deletes it.
- `app/forecast_handlers.py` — `fetch_forecast()` (deterministic charts via
  lazy `app.surf_forecast`) + `generate_reports()` (streams
  `app.generate_surf_report` markdown).
- `app/agent_trace.py` — trace coercion (`_coerce_scored_hours`,
  `_coerce_rank_rows`, `_coerce_forecast_hours`), telemetry builders,
  chart trios. `app/agent_chat.py` — `chat_fn` (lazy
  `from app import agent`, session-persistent `SurfAgent`), spot dropdown,
  leaderboard select.
- `app/ui.py` — `build_demo()` layout + event wiring only (no logic).

Conventions: lo-fi theme via `APP_CSS` (light blue bg `#d6e9f8`, dark blue
`#0b2c5c`, Courier). Don't restyle without asking. Keep callbacks wired in
`build_demo()` (`state_dd`/`region_dd`/`skill_dd` → `update_map`;
`break_dd` → `on_break_pick`; `generate_btn` → `generate_custom_break`;
`clear_btn` → `clear_custom_break`).

## `app/` map of the code

`app/generate_surf_break.py`:

- `MODEL_ID = "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16"`,
  `PROVIDER = "fireworks-ai"`. Swap only to a model actually served by an
  Inference Provider you have enabled.
- `load_prompt_parts()` reads schema + Bells example from `data/`.
- `build_surf_break_prompt(break_name, state, region)` — rules: JSON only,
  populate required fields, strict enums, real-world geography (not generic
  defaults), best-estimate coords, primary takeoff zone, 2–4 sentence
  description, copy state/region verbatim into top-level AND
  `location.state`/`location.region`.
- `extract_json()` tolerates ```fences, else grabs outermost`{...}`.
- `generate_surf_break(...)` — one `InferenceClient.chat.completions.create`
  call (temp 0.4, max_tokens 2048). Deliberately NOT a smolagents CodeAgent
  (ReAct `<code>` format conflicts with raw-JSON instruction — see module
  docstring). CLI: `python app/generate_surf_break.py [name] [state] [region]`.
- Needs `HF_TOKEN` env (Inference Providers access).

`app/generate_base_data.py`:

- `load_break_list()` flattens `Australia_Surf_Breaks: state → region →
[names]` into `{break_name, state, region}` in stable order.
- `enrich_result()` merges LLM output with canonical `state`/`region` from
  the input list + stable `id`; normalizes `location.state/region`.
- `load_existing_results()` / `save_results()` — resume-safe; accepts legacy
  dict format, writes sorted list by (state, region, name).
- `generate_with_retries()` — 2 attempts, linear backoff; failures are NOT
  persisted (missing entries retry next run).
- `main()` saves after every break + `REQUEST_DELAY = 1.0`s between calls.

## `data/` contracts

- Required break fields: `name`, `state`, `region`, `location`,
  `skillLevel`, `breakType`, `peakType`, `idealSwell`, `idealWind`,
  `idealTide`. Optional: `description`, `id`, `bestSeason`, `hazards`,
  `crowdFactor`. Never invent enum values — check
  `data/surf-break-schema.json` first.
- Canonical `state`/`region` always come from the input list, never the
  model. `location.country` is `"Australia"`.
- New prompts must load schema + example from `data/` (don't paste copies).

## `wavereader/` (deleted after port — see `app/agent.py` + `app/agent_tools.py`)

- Ported: `app/agent_tools.py` (deterministic forecast/score/knowledge
  functions over `data/australia-surf-breaks-enriched.json` via
  `app/forecasts.py` + `app/scoring.py` + `app/adapters.py`),
  `app/agent.py` (smolagents CodeAgent, HF Router, Nemotron defaults, trace
  capture, single Tool definitions).
- `main.py` "surf agent" tab chats via `SurfAgent.run_stream` and rebuilds
  score/swell/wind charts from the trace's `score_week` payload.
- The LLM never owns numbers — scores/forecasts stay deterministic.

## Rules for edits

1. `app/` is tracked in this repo (no nested git — don't re-init one).
2. Never commit `.env`, `.venv/`, `__pycache__/`, `.DS_Store` (all ignored).
3. Never read `.env` or print secrets/tokens. Use `.env.example` for var
   names; check presence with `printenv HF_TOKEN | wc -c` or
   `[ -n "$HF_TOKEN" ]` style checks that never echo the value.
4. Keep prompt files in `data/`; keep `main.py` free of embedded schema text.
5. Test cheaply: `uv run python -c "from pathlib import Path; import main"` for
   import health; full generation calls cost inference — use the single-break
   CLI before running the batch.
