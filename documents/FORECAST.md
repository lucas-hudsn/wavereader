# Surf forecast tab

The `surf forecast` tab in `main.py:build_demo()` scores the break
selected on the `encyclopedia` tab. Fully deterministic: Open-Meteo
numbers in, `scoring.py` numbers out. No agent/LLM in this path.

## Pipeline

```
pick break (tab 1, break_dd -> selected_break gr.State)
  -> press "Get forecast" (tab 2, fetch_btn)
  -> fetch_forecast() [main.py]
  -> _load_forecast() [importlib, app/surf_forecast.py, no package import]
  -> get_scored_week(break, skill, days)
       -> adapters.enriched_to_scoring_spot(break)   # schema -> scoring shape
       -> forecasts.get_forecast(lat, lng, days)     # marine + wind, cached
       -> scoring.score_week(forecast, spot, skill)  # 0-10 per hour
  -> best_window / daily_best / build_*_fig + tables
```

`fetch_forecast` shows `gr.Progress` steps and writes human-readable
status into `status_box`; any exception surfaces there with empty figs
(no traceback in UI).

## Adapter (`wavereader/adapters.py`)

`scoring.py` expects the old spot shape; the enriched schema differs,
so the adapter bridges it:

| scoring expects | enriched has | mapping |
|---|---|---|
| `ideal_swell.direction: "SE"` | `idealSwell.direction: ["E","ESE","SE"]` | `/`-join list (`_dir_to_deg` parses `/` as cyclic mean); empty → `"E"` |
| `ideal_swell.size_ft_min/max` | `idealSwell.sizeRangeFt.{min,max}` | float cast |
| `ideal_wind.direction` | `idealWind.direction: [...]` | same `/`-join; empty → `"E"` |
| `ideal_wind.strength_kt_max` | only `idealWind.type` (offshore/…) | flat `15.0` (`DEFAULT_WIND_MAX_KT`) — schema has no knots value; final limit is `min(15, skill_profile_max)` in `_score_wind` |
| skill `beginner/intermediate/advanced/expert` | + `pro-only` | `pro-only` → `expert`; unknown/None → `intermediate` |

Helpers: `normalize_skill()`, `break_skill()` (break's own tier),
`get_coords()` (mirrors `main.py _lat/_lng`, `None` on missing).

## Forecast client (`wavereader/forecasts.py`)

- Two Open-Meteo endpoints merged on `time` by `_build_normalized`:
  `marine-api.open-meteo.com` (hourly `wave_height`, `wave_period`,
  `wave_direction`, `wind_wave_height`, `swell_wave_height`) +
  `api.open-meteo.com` (hourly `wind_speed_10m` in km/h, converted to
  knots in `score_week`, + `wind_direction_10m`). Marine serves no wind.
- Grid snap: coords shift ~0.13° seaward (`_seaward_offset`: TAS/south
  coast south, east coast east, west coast west) so lookups land on a
  marine grid point.
- Cache: `.cache/forecasts/<lat>_<lon>_<days>.json` envelope
  `{fetched_at, data}`, TTL 6h (`CACHE_TTL_SECONDS`). Fresh cache served
  without network; on API failure the stale entry is served as fallback;
  raises only with no usable data at all. Horizon: hourly, 1–7 days
  (`days_slider`, clamped).

## Scoring (`wavereader/scoring.py`)

Per hour (`score_hour`), weights `swell_size 0.30 / swell_direction
0.20 / wind 0.30 / period 0.20` (redistributed when direction missing):

- **size** — 10 inside spot's `[min,max]`, Gaussian falloff outside,
  multiplied by skill comfort penalty → 0 above `max_safe_size_ft`.
- **direction** — Gaussian on angular diff to ideal (σ = 30°).
- **wind** — mean of speed (10 if ≤ limit else 0; glassy ≤5kt always 10)
  and direction (cosine falloff from offshore). Limit =
  `min(spot 15kt, skill max)`.
- **period** — 0 at ≤4s, linear to 10 at ≥14s, never penalised above.

`score_week` skips hours with nulls. Skill profiles (ft / kt / s):

| skill | comfort ft | max safe ft | max wind kt |
|---|---|---|---|
| beginner | 1.0–3.5 | 4.5 | 12 |
| intermediate | 2.0–6.5 | 8.5 | 18 |
| advanced | 3.0–12.0 | 18.0 | 25 |
| expert (+pro-only) | 4.0–30.0 | 50.0 | 35 |

## UI outputs (`app/surf_forecast.py` builders)

- `best_md` hero: `**score/10 @ time** — H m @ P s, wind Wkt (deg°)`.
- `build_score_fig` — time → score line (y 0–10) + best-hour marker.
- `build_components_fig` — 4 lines: `swell_size / swell_direction /
  wind / period`.
- `build_waves_fig` — `wave_height_m` + `wave_period_s` (right axis).
- `build_wind_fig` — `wind_speed_kt` line.
- `daily_df` — best hour per date via `daily_best`.
- `hourly_df` — every scored hour: time, score, 4 components, wave
  height/period, wind kt.
- Empty `scored` → figs annotated `No forecast data`, tables empty.

## Behaviour + limits

- Explicit **Get forecast** button — no auto-fetch on pick (saves API
  calls). Skill dropdown defaults to the selected break's tier; days
  default 7.
- Missing coords → `ValueError` → status error. No-break → warning
  state, no fetch.
- Custom ⭐ break works identically (same schema + coords).
- Known limits: no tide curves (Open-Meteo has none — `idealTide` is
  qualitative only); flat 15kt wind tolerance for all spots; swell
  direction is a cyclic mean of the ideal list, not a per-peak model.
