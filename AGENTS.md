# AGENTS.md

Guidance for AI coding agents working in this repo. The active surface is
`app.py` + `ui/` + `wavereader/` + `data/` (the v2 rebuild). `legacy/`
holds the frozen v1 front end (`main.py` + `app/`) — don't extend it; it
survives only as the fallback layer in `ui/_compat.py`.

## What is live now

- `app.py` — v2 entrypoint: `build()` + `gr.api` tools +
  `demo.launch(css=APP_CSS, mcp_server=True)`. Run `uv run python app.py`.
- `ui/` — the single-page front end (no tabs): `app.py` (layout + wiring,
  ≤3 `gr.State`; Bells Beach auto-selected on load so there are no empty
  states), `panels/{lens,story,intel,agent}.py` (map-lens column | forecast
  story | intel rail | full-width agent bar), `charts/{strip,score,seafloor,climate,map,_style}.py`,
  `contracts.py` (`SELECT_KEYS`/`FETCH_KEYS`/`AGENT_KEYS` + `fill()` —
  handlers return via `fill(KEYS, …)` so output ordering can't drift),
  `_compat.py` (backend access: v2 core → `legacy.app.*` → stubs; also
  wetsuit hints, engine chips, surf cams), `theme.py` (`APP_CSS`, IBM Plex
  Mono lo-fi identity — don't restyle without asking).
- `wavereader/` — pure core, typed + tested, no Gradio imports:
  `breaks.py` (catalogue, memoized `load_breaks`), `openmeteo.py`
  (versioned/atomic disk cache, seaward grid-snap), `scoring.py` (deterministic
  0–10 engine — the LLM never owns numbers), `seafloor.py` (GEBCO world model),
  `climate.py` (ERA5 5-yr profiles + audit; `break_climate` reads the
  profile embedded on each break record, per-slug file fallback), `tools.py`
  (the typed tool functions shared by agent + MCP), `agent.py`
  (smolagents `ToolCallingAgent`,
  native tool calls, budget: 6 steps / 2 score_week / 700 tokens),
  `narrate.py` + `llm.py` (one InferenceClient factory:
  Nemotron 3 Ultra via deepinfra, `WR_*` env overrides).
- `scripts/warm_caches.py` — pre-fill forecast + seafloor caches (demo hot
  start). `scripts/build_climate.py` — climatology builder (re-embeds built
  profiles into the catalogue after each run, backup first).
- `scripts/check_coords.py` + `scripts/check_coast.py` — break-coordinate
  maintenance: `check_coords` validates/fixes state/region/duplicate
  placement against OSM; `check_coast` audits GEBCO elevation at every
  break point and (`--fix`) snaps non-coastal ones to the nearest 0 m
  shoreline crossing (both write a timestamped backup first).
- `data/` — `australia-surf-breaks-enriched.json` (238 breaks; each record
  embeds its ERA5 profile under `climate` — 236 of 238, the two duplicate
  Gnaraloo rows have no profile),
  `surf-break-schema.json` (contract), `climate/*.json` (per-slug ERA5
  profiles — `build_climate.py` output and `break_climate`'s fallback;
  also `index.json` manifest), `surf-cams.json` (camera links keyed
  `"name | state | region"`), `surf-break-example-bells.json` (prompt worked
  example).

## Deploying to HF Spaces

- The Space `lucashudsn/wavereader` (public) *is* this repo — remote
  `space`. Ship with `scripts/deploy_space.sh` (builds a throwaway commit
  that prepends `space-config.yaml` to `README.md` and pushes it to
  `space:main` — Spaces need YAML frontmatter, GitHub doesn't have to see
  it), then `git push origin v2` to keep GitHub in sync. The Space builds
  from the pushed commit; watch *Logs → Build* on the Space page or poll
  `HfApi().get_space_runtime("lucashudsn/wavereader")` until `RUNNING`.
- `space-config.yaml` is the Space config. Keep
  `sdk_version` in lockstep with the gradio pin in `requirements.txt`
  (regenerate that file only via `uv export --no-hashes
  --format requirements-txt --no-dev -o requirements.txt` — other
  invocations can leave stray progress lines that break pip), and
  `python_version` in lockstep with `pyproject.toml`'s `requires-python`.
  If you change Space settings via the web UI, HF rewrites the Space's
  `README.md` — mirror anything you care about back into the yaml.
- `HF_TOKEN` is a Space secret (set once via *Settings → Variables and
  secrets* or `HfApi().add_space_secret`); `WR_*` overrides can be added
  the same way. `.cache/` is ephemeral on the Space and rebuilds lazily —
  no persistent storage, no warm step.

## Conventions that matter

- One spot drives everything: `selected` (gr.State) is the single source of
  truth — picking a spot re-aims the map, badges, forecast strip, world
  model and climatology together. Keep it that way.
- Staged spin-ups: `ui/panels/story.py::fetch_forecast` is a **generator**
  that yields stage 1 (charts, ~ms) then stage 2 (seafloor world model from
  a parallel thread). Status lines name the engine + latency. Keep that
  pattern for anything slow.
- Charts: theme through `ui/charts/_style.py::style_fig`; weekend shading
  via `add_weekend_shading`. The week strip lives in `charts/strip.py`
  (score/swell/wind rows); window slicing (weekend/mornings/arvos) re-charts
  from state via `filter_hours` — no refetch. Seafloor display is bicubically
  smoothed (scipy) and its wave animation is period-driven — smoothing and
  animation are display-only; stats stay on the raw grid.
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
