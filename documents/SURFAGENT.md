# Surf agent tab

Agentic chat in `app/ui.py:build_demo()` (toggle `agentic mode`). Two layers:

- **Reasoning** (`app/agent.py`): smolagents `CodeAgent` on Hugging Face
  Inference Providers (`provider="fireworks-ai"`, `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16`).
- **Numbers** (`app/agent_tools.py`): deterministic forecast/score/knowledge
  functions over `data/australia-surf-breaks-enriched.json`. The only
  network access is `app.forecasts.get_forecast` (disk-cached Open-Meteo);
  scoring stays in `app.scoring`, spot shaping in `app.adapters`.

Contract: the LLM interprets and explains only — every wave height, wind
speed, and score MUST come from a tool. Charts are built from trace
payloads, never from LLM text.

## Model config (`app/agent.py`)

| constant | value |
|---|---|
| `HF_DEFAULT_MODEL` (:148) | `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16` |
| `PROVIDER` (:149) | `fireworks-ai` |
| `MODEL_TEMPERATURE` / `MODEL_MAX_TOKENS` / `MODEL_TIMEOUT` | `0.2` / `1500` / `120` |
| `AGENT_MAX_STEPS` (:154) | `10` |
| `MAX_OBSERVATION_CHARS` (:160) | `4000` (trace preview truncation) |

`_build_model` (:554): token priority explicit `hf_token` arg > `HF_TOKEN`
env; raises `ValueError` with a token-setup hint when missing.
`_load_prompt_templates` (:579) appends `SYSTEM_PROMPT` to smolagents'
default `code_agent.yaml`. `run_agent` (:900) / `run_agent_stream` (:911)
are thin constructors; `__main__` is a streaming CLI demo.

## System prompt (`app/agent.py:43`)

- **Rules 1–8**: never compute scores/forecasts/rankings; cite the tool
  name with numbers; tides are qualitative only (Open-Meteo has none);
  `get_spot_knowledge` first for spot questions; concise/actionable; never
  describe plots; **every recommended spot MUST have a `score_week` (or
  `get_forecast`) call** so its graphs render — never recommend from
  memory/knowledge alone.
- **Output contract**: one-line verdict → 1–3 scored picks (day/time +
  score + wave + wind) → one WHY sentence (cite `explain_score_breakdown`
  components) → hazards/skill footer → graphs line.
- **Few-shots**: A) single-spot timing (`knowledge → score_week`);
  B) "where in NSW" (`score_region_week → score_week` top pick, runner-up
  from the sweep table); C) A-vs-B compare (≤3 `score_week` calls, or
  `find_best_windows` per spot).
- **Workflow**: "where in \<region\>" → ONE `score_region_week` sweep
  (never loop `score_week`), then `score_week` the top pick for charts.
- **Budget**: ≤3 `score_week` calls per question; `score_region_week`
  counts as one. `find_best_windows` preferred for morning/weekend filters.
- **Stance** (advice only, never scores): goofy → lefts, natural → rights,
  A-frames neutral, via `peakType`. **Safety**: one-line caution on hazards
  or expert/pro-only; never send beginners to pro-only spots (redirect via
  `find_similar_spots`). **Ambiguity**: on not-found, `find_spots` + ask,
  never guess. **Dates**: resolve relative dates against tool timestamps;
  ~7-day window only.

## Tools

Region args accept a full state name, a sub-region (`Central Coast`), or a
legacy code (`NSW/QLD/VIC/WA/SA/TAS`, expanded in
`agent_tools.py:_expand_state_code`). Skill args normalize via
`adapters.normalize_skill` (pro-only → expert). `_BREAKS` (:132) loads at
import (list or legacy `{id: record}` dict, `error` rows dropped).

### Forecast + score

- `score_week(spot_name, region?, skill?)` (:209, tool :276) — ONE spot per
  call. Returns `{spot, skill, scored (full hourly rows), daily (per-date
  bests), best (top hour)}`. Token-heavy by design: the UI charts it.
- `get_forecast(spot_name, region?)` (:192, tool :263) — raw 7-day
  `{"hourly": [...], "daily": {sunrise/sunset}}` frame (chartable swell +
  wind, unscored).
- `score_region_week(region, skill?, break_type?, peak_type?, max_crowd?, avoid_hazards?, weekend_only?, min_score?, limit?)`
  (:461, tool :372) — PREFERRED for "where + when in \<region\>": one
  ThreadPool fan-out (8 workers) scores the whole region. Each spot carries
  slim `best` + per-date `daily` bests (`_slim_hour`, :418) — NOT full
  hourly rows, so follow with ONE `score_week` on the top pick for charts.
  `weekend_only` restricts daily/best to Sat/Sun; `min_score` drops spots
  below the floor; `limit` 1–15 (default 10). State-wide sweeps (>25
  matches) score the first 25 and say so in `coverage_note`. Empty result
  returns `spots: []` + a `list_states_regions()` hint, not an error.
- `rank_spots_this_week(region, skill?, break_type?, peak_type?, max_crowd?, avoid_hazards?, limit?)`
  (:317, tool :331) — lean leaderboard fallback: sorted
  `[{name, region, best_score, best_time, skill_level}]`, no daily bests.
  `limit` 1–25. Prefer the sweep when per-spot timing matters.

Shared deterministic filters (`_apply_spot_filters`, :379) run before
scoring so the LLM never filters by hand: exact `break_type`/`peak_type`
match, `max_crowd` cap over quiet\<moderate\<busy\<very crowded,
`avoid_hazards` drops breaks carrying a listed hazard. Fetch/score failures
are skipped (named in sweep `skipped`), never raised.

### Search + knowledge (network-free)

- `find_spots(query?, region?, skill?, limit?)` (:269, tool :294) —
  substring search over name/state/region (codes expanded); `region` is an
  alias for `query`. Returns trimmed
  `{name, state, region, skillLevel, breakType, peakType}`.
- `get_spot_knowledge(spot_name, region?)` (:180, tool :318) — trimmed
  profile (ideals, skill, hazards, crowd, description, location).
- `list_states_regions()` (:612, tool :510) — canonical `{states,
  regions_by_state}` vocabulary; call instead of guessing spellings.
- `find_similar_spots(spot_name, region?, skill?, limit?)` (:824, tool
  :486) — deterministic similarity (same skill +3, breakType +2, peakType
  +2, shared swell direction +1.5, size-range closeness, same state +1).

### Explain + filter

- `explain_score_breakdown(spot_name, region?, skill?, time?)` (:661, tool
  :422) — WHY one hour scored what it did: `components`
  (swell_size/swell_direction/wind/period) + raw inputs. `time` is a
  substring match, default = best hour. Call before narrating components.
- `find_best_windows(spot_name, region?, skill?, daypart?, weekend_only?, min_score?, max_wind_kt?, limit?)`
  (:708, tool :447) — deterministic post-filter over one spot's scored
  week. `daypart`: morning (05–11) / midday (11–15) / afternoon (15–20) /
  all. Returns `{spot, skill, filters, windows (slim, ≤10), best}`.
- `get_spot_sun_sst(spot_name, region?)` (:630, tool :523) — daily
  sunrise/sunset + latest sea-surface temp from the cached frame, plus a
  deterministic `wetsuit_hint` SST lookup (not LLM advice).

Name resolution (`_resolve_break`, :159): exact case-insensitive match
first, then substring; region-matching records win ties.

## Trace architecture (`app/agent.py`)

- `TraceEvent` (:228) / `AgentTrace` (:237): `{type, timestamp, data}`
  events; full observation kept under `observation`, ~4000-char preview
  under `observation_preview` (`_observation_preview`, :170) + `truncated`
  flag so chart payloads survive intact.
- **Why the wrappers**: CodeAgent executes tools *inside* the
  `python_interpreter` code step, so smolagents only yields
  `ToolCall(python_interpreter)` — no per-tool payloads. `_make_traced_tools`
  (:615) clones each `TOOLS` prototype per agent and wraps `forward`
  (`_wrap_forward`, :635) to record `tool_call`/`tool_result` events and
  queue `("tool_start"/"tool_end", …)` stream items (flushed FIFO by
  `_flush_pending_stream`, :724). Prototypes stay clean across sessions.
- `run` (:794) captures via `_traced_step_stream`, skipping the
  `python_interpreter` pseudo-calls. `run_stream` (:811) yields `("model",
  delta)` tokens, `("final", answer)`, backward-compat `("tool", name)`,
  richer `("tool_start"/"tool_end", {name, ms, summary, observation,
  arguments})`, and `("code", code_text)`. `_summarize_observation` (:181)
  makes per-tool one-liners (scored-hour counts, sweep/rank tops, window
  counts, breakdowns, SST hints).

## UI wiring (agent tab in `app/ui.py`, handlers in `app/agent_chat.py`)

- `chat_fn` (:1871): session-persistent `SurfAgent` in `gr.State` (rebuilt
  on token change; last 6 turns prepended on rebuild). Injects a hint
  (skill, encyclopedia pick > pref state/region, stance, morning/weekend
  daypart). Streams `run_stream`: progressive per-spot score/swell/wind
  charts (`live_spots`), forecast duo charts (`live_forecasts`), and the
  leaderboard (`live_rank`) land *before* the final answer; final render
  rebuilds everything from `_agent_chart_data(trace)` (:1255).
- Coercers accept trace-stringified payloads (JSON or repr):
  `_coerce_scored_hours` (:1121, list / `{scored}` / `{windows}` shapes),
  `_coerce_rank_rows` (:1198, list / `{rank}` / sweep `{spots}` shapes),
  `_coerce_forecast_hours` (:1711, raw `{hourly}` → scored-hour key shape).
- `_format_rank_table` (:1372) renders rank AND sweep payloads identically;
  `on_rank_select` (:2488) turns a leaderboard click into a drill-down
  question (the table has no hourly rows — the follow-up `score_week`
  produces the graphs). `on_agent_spot_change` (:1850) re-charts the
  dropdown pick. `clear_agent_chat` (:2466) resets session/history/charts.
- Telemetry: `_build_agent_telemetry` (:1482) pairs calls/results by id
  (FIFO fallback); `_summarize_result` (:1399) and `_human_tool_status`
  (:1603, e.g. "Sweeping Gold Coast (weekend) for intermediate…") keep the
  status box human-readable.

## Behaviour + limits

- Sweep payloads carry daily bests, not hourly rows — charts always require
  the follow-up `score_week` (system-prompt rule 8 enforces this).
- No tide curves anywhere (Open-Meteo serves none); `idealTide` is
  qualitative. Wind tolerance is a flat 15kt spot cap (`adapters.py`).
- The agent-tab skill dropdown has no pro-only tier (encyclopedia picks map
  pro-only → expert). Skill mismatch returns empty sweeps (e.g. no
  beginner breaks on the Gold Coast) rather than mis-scored spots.
- Cost: tools serve 6h-TTL disk cache first; a cold region sweep fans out
  ~10–25 fetches (sub-regions ≈ 10 spots, states truncated at 25).
