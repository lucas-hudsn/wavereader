# wave~reader

Australian surf-break encyclopaedia + scored surf forecast (two Gradio tabs).

Tab 1 (`encyclopedia`) filters spots on a Plotly `Scattermap` and shows
break details. Tab 2 (`surf forecast`) is two-stage: Stage 1 fetches
Open-Meteo marine + wind data for the selected break and scores every
hour 0–10 (deterministic); Stage 2 optionally streams a short LLM
dot-point report that narrates those scores. The LLM never owns
numbers — generation lives in `app/generate_surf_break.py` /
`app/generate_surf_report.py`, scores/forecasts stay deterministic in
`app/scoring.py` + `app/forecasts.py`.

## Layout

```
main.py                          # Gradio two-tab front end (run this)
app/
  generate_surf_break.py         # single-shot structured-JSON break generator
  generate_base_data.py          # batch/resumable enrichment runner
  surf_forecast.py               # scored-forecast service + Plotly builders (no Gradio)
  generate_surf_report.py        # Stage-2 streamed LLM report (narrates scores only)
  forecasts.py                   # Open-Meteo marine + weather client, disk cache
  scoring.py                     # deterministic 0–10 surf-quality engine
  adapters.py                    # enriched-break -> scoring-spot bridge (flat 15kt wind)
data/
  australia-surf-breaks.json           # input: nested state -> region -> [names]
  australia-surf-breaks-enriched.json  # output: list of schema-valid breaks
  surf-break-schema.json               # JSON Schema every break must conform to
  surf-break-example-bells.json        # worked example (Bells Beach) used in the prompt
wavereader/                      # legacy-kept, not wired into the UI
  agent.py / tools.py            # agentic forecast-explanation layer (kept for later)
documents/
  ENCYCLOPEDIA.md                # encyclopedia tab deep dive
  FORECAST.md                    # forecast tab deep dive (pipeline, scoring, cache, report)
```

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14 (`uv sync` reads
`.python-version`).

```sh
uv sync
cp .env.example .env   # then fill in HF_TOKEN
```

`HF_TOKEN` (Inference Providers access,
https://huggingface.co/settings/tokens) is needed for break generation
(`app/generate_surf_break.py`) and the Stage-2 surf report
(`app/generate_surf_report.py`). The Stage-1 forecast charts need
network access to Open-Meteo, with disk cache fallback under `.cache/`
(git-ignored).

## Run the front end

```sh
uv run python main.py
```

Two tabs share one `selected_break` state:

- **encyclopedia** — State / Region / Skill filters reframe the
  `Scattermap`. Hover a dot for name + region + skill; pick a break for
  its details table. "Can't find your local break?" generates one live
  via `app/generate_surf_break.py` — session-only (`gr.State`, never
  written to `data/`). See `documents/ENCYCLOPEDIA.md`.
- **surf forecast** — pick a break on tab 1, then press **Get forecast
  (charts)** on tab 2. Skill defaults to the break's own `skillLevel`
  (`pro-only` → `expert`); window is fixed at 7 days. Shows a best-window
  hero, score bars (red → green, gold ★ on the best hour), swell
  height + period chart, and a wind-arrows strip (colour = direction
  quality, size = strength). Then optionally press **Generate surf
  report ✨** for a streamed dot-point write-up (one bullet per day +
  `**Recommendation: …**`). See `documents/FORECAST.md`.

## Generate break data

Single break (prints JSON):

```sh
uv run python app/generate_surf_break.py "Kilcunda" "Victoria" "Bass Coast"
```

Full batch (resumable — skips breaks already in the enriched output,
retries missing ones on re-run, saves after every break):

```sh
export HF_TOKEN=hf_xxx
uv run python app/generate_base_data.py
```

How it works: `build_surf_break_prompt()` assembles schema + Bells Beach
worked example + target break; `generate_surf_break()` makes one chat
completion call (`nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16` via
`provider="deepinfra"`, temp 0.4, 2048 tokens); `extract_json()` strips
fences / outermost `{...}` and parses. `enrich_result()` pins canonical
`state`/`region` from the input list (not the model) plus a stable
`"<name> | <state> | <region>"` id.

## Schemas

- `data/surf-break-schema.json` — required: `name`, `state`, `region`,
  `location` (region/state/country/coordinates), `skillLevel`,
  `breakType`, `peakType`, `idealSwell`, `idealWind`, `idealTide`.
  Enums are strict (compass points, skill tiers, break/peak types,
  tide stages, seasons, hazards, crowd factor).
- `data/surf-break-example-bells.json` — the prompt's worked example.
- `data/australia-surf-breaks.json` — the nested input list.
- `data/australia-surf-breaks-enriched.json` — the generated output
  (list, sorted by state/region/name on write).

## Forecast pipeline (short)

Stage 1 (`main.py fetch_forecast` → `app/surf_forecast.get_scored_week`):
break → `adapters.enriched_to_scoring_spot` → `forecasts.get_forecast`
→ `scoring.score_week` → score / swell / wind figs + `scored_payload`
(best + daily bests + scored hours). Wind tolerance is a flat `15kt`
(`adapters.DEFAULT_WIND_MAX_KT`) because the schema carries no
wind-strength number.

Stage 2 (`main.py generate_reports` →
`app/generate_surf_report.generate_surf_report_stream`): the prompt
carries only the daily bests (≤7 lines) + best window + a one-line
break summary; the model streams plain markdown (one bullet per day +
`Recommendation` line) with reasoning disabled (`/no_think` +
`reasoning_effort: "none"`). It narrates the provided scores only.
Full detail in `documents/FORECAST.md`.

## Kept for later

`wavereader/agent.py` / `wavereader/tools.py` are the legacy agentic
forecast-explanation layer. Not wired into the UI — the forecast tab
is Stage-1 deterministic plus the Stage-2 `generate_surf_report.py`
narrator by design.
