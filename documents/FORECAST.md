# Surf forecast tab

The `surf forecast` tab in `app/ui.py:build_demo()` scores the break
selected on the `encyclopedia` tab. Two stages:

- **Stage 1 — deterministic charts** (`fetch_forecast`): Open-Meteo
  numbers in, `scoring.py` numbers out. No agent/LLM in this path.
- **Stage 2 — narrated report** (`generate_reports`, opt-in): the LLM
  narrates the Stage-1 scores only — it never invents swell/wind/score
  values.

## Pipeline

```
pick break (tab 1, break_dd -> selected_break gr.State)
  -> press "Get forecast (charts)" (tab 2, fetch_btn)
   -> fetch_forecast() [app/forecast_handlers.py]
   -> lazy `from app import surf_forecast` (direct package import)
  -> get_scored_week(break, skill, days=7)
       -> adapters.enriched_to_scoring_spot(break)   # schema -> scoring shape
       -> forecasts.get_forecast(lat, lng, days)     # marine + wind, cached
       -> scoring.score_week(forecast, spot, skill)  # 0-10 per hour
  -> best_window / daily_best / build_score_fig / build_waves_fig / build_wind_fig
  -> scored_payload gr.State {break, skill, spot, scored, daily, best, days}
  -> press "Generate surf report" (tab 2, report_btn) [optional]
   -> generate_reports() [app/forecast_handlers.py]
   -> lazy `from app import generate_surf_report` (direct package import)
  -> generate_surf_report_stream(break, skill, daily, best, days)
```

`fetch_forecast` fixes `days = 7` (no days slider in the UI;
`get_scored_week` still clamps any `days` arg to 1–7). It shows
`gr.Progress` steps and writes human-readable status into `status_box`
plus a tool-call trace into `report_telemetry_box`; any exception
surfaces there with empty figs (no traceback in UI). An empty `scored`
list disables the report path (`scored_payload = None`).

## Adapter (`app/adapters.py`)

`scoring.py` expects the old spot shape; the enriched schema differs,
so the adapter bridges it:

| scoring expects | enriched has | mapping |
|---|---|---|
| `ideal_swell.direction: "SE"` | `idealSwell.direction: ["E","ESE","SE"]` | `/`-join list (`_dir_to_deg` parses `/` as cyclic mean); empty → `"E"` |
| `ideal_swell.size_ft_min/max` | `idealSwell.sizeRangeFt.{min,max}` | float cast (missing → `0.0`) |
| `ideal_wind.direction` | `idealWind.direction: [...]` | same `/`-join; empty → `"E"` |
| `ideal_wind.strength_kt_max` | only `idealWind.type` (offshore/…) | flat `15.0` (`DEFAULT_WIND_MAX_KT`) — schema has no knots value; final limit is `min(15, skill_profile_max)` in `_score_wind` |
| skill `beginner/intermediate/advanced/expert` | + `pro-only` | `pro-only`/`pro only`/`pro` → `expert`; unknown/None → `intermediate` |

Helpers: `normalize_skill()`, `break_skill()` (break's own tier),
`get_coords()` (mirrors `app/maps.py` `_lat`/`_lng`, `None` on missing).

## Forecast client (`app/forecasts.py`)

- Two Open-Meteo endpoints merged on `time` by `_build_normalized`:
  `marine-api.open-meteo.com` (hourly `wave_height`, `wave_period`,
  `wave_direction`, `wind_wave_height`, `swell_wave_height`) +
  `api.open-meteo.com` (hourly `wind_speed_10m` in km/h, converted to
  knots in `score_week`, + `wind_direction_10m`). Marine serves no wind.
- Grid snap: coords shift ~0.13° seaward (`_seaward_offset`, rounded to
  2 dp by `_round_coords`) so lookups land on a marine grid point —
  TAS (`lat <= -39.5`) shifts south, east coast (`lon >= 147`) shifts
  east, west coast (`lon <= 125`) shifts west, otherwise (SA/VIC south
  coast) shifts south.
- Cache: `.cache/forecasts/<lat>_<lon>_<days>.json` envelope
  `{fetched_at, data}` (key from the *raw* spot coords; the seaward
  offset is a fetch detail only). TTL 6h (`CACHE_TTL_SECONDS`). Fresh
  cache served without network (written atomically via tmp + rename);
  on API failure the stale entry is served as fallback (legacy
  pre-envelope files return with `fetched_at = 0` so they still work
  as stale fallback); raises only with no usable data at all.

## Scoring (`app/scoring.py`)

Per hour (`score_hour`), weights `swell_size 0.30 / swell_direction
0.20 / wind 0.30 / period 0.20` (redistributed when direction missing):

- **size** — 10 inside spot's `[min,max]`, Gaussian falloff outside
  (`σ = max(1.0, min*0.4)` below, `σ = max(1.5, max*0.5)` above),
  multiplied by skill comfort multiplier → 0 above `max_safe_size_ft`.
- **direction** — Gaussian on angular diff to ideal
  (`σ = 45/1.5 = 30°`, so 45° off ≈ 3.2/10).
- **wind** — mean of speed (10 if ≤ limit else 0; glassy ≤5kt always 10)
  and direction (`10 * max(0, cos(diff/2))`, i.e. perfect offshore →
  10, 180° off (onshore) → 0). Limit =
  `min(spot 15kt, skill max)`.
- **period** — 0 at ≤4s, linear to 10 at ≥14s, never penalised above.

`score_week` skips hours with nulls and converts `wind_speed_10m`
km/h → kt (`× 0.539957`). Skill profiles (ft / kt / s):

| skill | comfort ft | max safe ft | max wind kt |
|---|---|---|---|
| beginner | 1.0–3.5 | 4.5 | 12 |
| intermediate | 2.0–6.5 | 8.5 | 18 |
| advanced | 3.0–12.0 | 18.0 | 25 |
| expert (+pro-only) | 4.0–30.0 | 50.0 | 35 |

## UI outputs (`app/surf_forecast.py` builders)

`get_scored_week` returns `{forecast, scored, spot, skill, lat, lng}`.
`daily_best` groups by date (first 10 chars of `time`) and returns
`{date, time, score, wave_height_m, wave_period_s, wind_speed_kt,
wind_direction_deg}` per day. `best_window` is the single
highest-scoring hour.

- `best_md` hero: `**score/10 @ time** — H m @ P s, wind Wkt (deg°)`.
- `build_score_fig` — score bars coloured red → green by quality
  (≥8 dark green, ≥6 light green, ≥4 yellow, ≥2 orange, else red) +
  gold ★ marker on the best hour.
- `build_waves_fig` — `wave_height_m` filled area (blue, left axis) +
  `wave_period_s` line (orange, right axis).
- `build_wind_fig` — arrows only, no y-axis: colour = direction
  quality vs the spot's ideal offshore (green ≤45°, yellow cross
  ≤135°, red onshore above that; dark blue when the spot has no
  parseable direction), size = strength (22 → 33pt over 0–30kt),
  subsampled to ~28 arrows. Arrows point where the wind blows TO;
  exact kt + compass on hover.
- All three share `_strip_layout` styling (compact heights, unified
  hover, white plot bg). `build_components_fig` is retired (returns
  `No forecast data`) — use `build_score_fig`.
- Empty `scored` → figs annotated `No forecast data`, report disabled.

## Stage-2 report (`app/generate_surf_report.py`)

Same framework as break generation (single-shot `InferenceClient`
call, `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16` via
`provider="fireworks-ai"`, deliberately NOT a smolagents CodeAgent).
Speed-first: the prompt carries ONLY the daily bests (≤7 lines) + the
single best window + a one-line break summary (ideals + up to 3
hazards) — never the full hourly table or full break record.

- Output is plain markdown, NOT JSON: one `- ` bullet per day in date
  order (date, score, height/period, wind, short outlook phrase) plus
  a final `**Recommendation: <date + time> -- <reason>.**` line.
  `max_tokens=500`, `temperature=0.3`.
- Reasoning disabled at the API level (`EXTRA_BODY =
  {"reasoning_effort": "none"}` + `/no_think` system prompt). Markers
  `@@REPORT@@ … @@END@@` fence the answer; `_clean_output` strips
  `<think>` blocks, fences, and plain-text planning sentences
  ("we need to…") live during streaming.
- `generate_surf_report_stream` yields the accumulated cleaned report
  per delta; `stats` reports `reasoning_chars` (hidden channel, never
  displayed) vs `content_chars` so callers can prove the visible text
  is the final report. `app/forecast_handlers.py` `generate_reports` yields an instant
  "Contacting report model…" placeholder first so the button never
  looks dead, then streams. LLM failure keeps the deterministic
  charts — only the report box shows the error.

## Behaviour + limits

- Explicit **Get forecast** button — no auto-fetch on pick (saves API
  calls). Skill dropdown defaults to the selected break's tier
  (`pro-only` → `expert`); window fixed at 7 days. Report is a second
  explicit opt-in after inspecting the charts.
- Missing coords → `ValueError` → status error. No-break → warning
  state, no fetch. No scored hours → warning, report disabled.
- Custom ⭐ break works identically (same schema + coords).
- Known limits: no tide curves (Open-Meteo has none — `idealTide` is
  qualitative only); flat 15kt wind tolerance for all spots; swell
  direction is a cyclic mean of the ideal list, not a per-peak model.
