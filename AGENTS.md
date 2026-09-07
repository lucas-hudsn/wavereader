# AGENTS.md

Guidance for AI coding agents working in this repo. The active surface is
`main.py` + `app/` + `data/`. `wavereader/` is legacy-kept, to reimplement.

## What is live now

- `main.py` — Gradio map front end. Run with `uv run python main.py`.
- `app/generate_surf_break.py` — single-shot structured-JSON generator.
- `app/generate_base_data.py` — batch/resumable enrichment runner.
- `data/` — `australia-surf-breaks.json` (input list),
  `australia-surf-breaks-enriched.json` (generated output),
  `surf-break-schema.json` (conformance contract),
  `surf-break-example-bells.json` (prompt worked example).

## `main.py` map of the code

Entry: `build_demo()` → `main()` → `demo.launch(css=APP_CSS)`.

- Data load (module import time): `load_breaks()` reads
  `data/australia-surf-breaks-enriched.json` into `DF` (handles legacy
  `{"name | state | region": {...}}` dict format too, drops `error` rows).
  Derives `STATES`, `REGIONS_BY_STATE`, `ALL_REGIONS`, `SKILLS`.
- Filtering: `filter_breaks(df, state, region, skill)` — `"All"`/None = no
  filter. Case-insensitive on canonical `state` / `region` / `skillLevel`.
- Map: `build_map(records, default_view)` — Plotly `Scattermap`
  (`open-street-map` style), marker colour by `SKILL_COLORS`, point order ==
  records order so the break list lines up. Auto-centers/zooms via
  `_zoom_for_span()` unless `default_view` (unfiltered → whole Australia).
  `build_map_with_custom()` adds the gold star marker for the session break.
- Details: `break_to_table(break_)` flattens one record to a
  Field/Value dataframe (name/state/region/description/skill/break+peak
  type/coords/ideal swell+wind+tide/season/hazards/crowd).
- Session-only custom break: `generate_custom_break()` streams
  `(telemetry, details, map, dropdown, state)` tuples via `yield`.
  Loads `app/generate_surf_break.py` with `_load_generator()`
  (`importlib`, no package import). Empty custom state/region fields fall
  back to the main map filters; explicit values win. Exactly one custom
  break per session (`gr.State`, never written to disk); regeneration
  replaces it. `clear_custom_break()` deletes it. `sync_custom_from_filters()`
  pushes map State/Region into the generation form (`gr.skip()` leaves a
  field untouched when the filter is `All`).
- Identity: `_resolve_pick()` maps a break-list label back to its record
  (custom break carries a `⭐ (your break)` suffix); base records match by
  `name`. Enriched `id` is `"<name> | <state> | <region>"`.
- Helpers `_lat()` / `_lng()` return None on missing coords (map skips
  them for centering); `_join()` stringifies list fields.

Conventions: lo-fi theme via `APP_CSS` (light blue bg `#d6e9f8`, dark blue
`#0b2c5c`, Courier). Don't restyle without asking. Keep callbacks wired in
`build_demo()` (`state_dd`/`region_dd`/`skill_dd` → `update_map`;
`break_dd` → `on_break_pick`; `generate_btn` → `generate_custom_break`;
`clear_btn` → `clear_custom_break`).

## `app/` map of the code

`app/generate_surf_break.py`:

- `MODEL_ID = "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16"`,
  `PROVIDER = "deepinfra"`. Swap only to a model actually served by an
  Inference Provider you have enabled.
- `load_prompt_parts()` reads schema + Bells example from `data/`.
- `build_surf_break_prompt(break_name, state, region)` — rules: JSON only,
  populate required fields, strict enums, real-world geography (not generic
  defaults), best-estimate coords, primary takeoff zone, 2–4 sentence
  description, copy state/region verbatim into top-level AND
  `location.state`/`location.region`.
- `extract_json()` tolerates ``` fences, else grabs outermost `{...}`.
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

## `wavereader/` (kept, to reimplement — do not delete)

- `agent.py` (smolagents CodeAgent, HF Router, Nemotron defaults, trace
  capture), `tools.py` (forecast/score/knowledge wrappers + Tool classes),
  `forecasts.py` (Open-Meteo marine+weather client, disk cache),
  `scoring.py` (deterministic 0–10 surf-quality engine).
- They still assume the old data layout (`spots.py`, since removed). Rewire
  them to `data/australia-surf-breaks-enriched.json` + the
  `surf-break-schema.json` contracts and to the `main.py` UI before using
  them in the demo path. The LLM never owns numbers — scores/forecasts stay
  deterministic.

## Rules for edits

1. `app/` is tracked in this repo (no nested git — don't re-init one).
2. Never commit `.env`, `.venv/`, `__pycache__/`, `.DS_Store` (all ignored).
3. Keep prompt files in `data/`; keep `main.py` free of embedded schema text.
4. Test cheaply: `uv run python -c "from pathlib import Path; import main"` for
   import health; full generation calls cost inference — use the single-break
   CLI before running the batch.
