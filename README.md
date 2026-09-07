# wave~reader

Australian surf-break encyclopaedia + deterministic surf forecast (two Gradio tabs).

Tab 1 (`encyclopedia`) filters spots on a Plotly `Scattermap` and shows
break details. Tab 2 (`surf forecast`) fetches Open-Meteo marine + wind
data for the selected break and scores every hour 0–10. The LLM never
owns numbers — generation lives in `app/`, scores/forecasts stay
deterministic in `wavereader/`.

## Layout

```
main.py                          # Gradio two-tab front end (run this)
app/
  generate_surf_break.py         # single-shot structured-JSON break generator
  generate_base_data.py          # batch/resumable enrichment runner
  surf_forecast.py               # scored-forecast service + Plotly builders (no Gradio)
  forecasts.py                   # Open-Meteo marine + weather client, disk cache
  scoring.py                     # deterministic 0–10 surf-quality engine
  adapters.py                    # enriched-break -> scoring-spot bridge (flat 15kt wind)
data/
  australia-surf-breaks.json           # input: nested state -> region -> [names]
  australia-surf-breaks-enriched.json  # output: list of schema-valid breaks
  surf-break-schema.json               # JSON Schema every break must conform to
  surf-break-example-bells.json        # worked example (Bells Beach) used in the prompt
wavereader/
  agent.py / tools.py            # kept, agent not wired into UI yet
documents/
  ENCYCLOPEDIA.md                # encyclopedia tab deep dive
  FORECAST.md                    # forecast tab deep dive (pipeline, scoring, cache)
```

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14 (`uv sync` reads
`.python-version`).

```sh
uv sync
cp .env.example .env   # then fill in HF_TOKEN
```

`HF_TOKEN` (Inference Providers access,
https://huggingface.co/settings/tokens) is only needed for break
generation (`app/`). The forecast tab needs network access to Open-Meteo,
with disk cache fallback under `.cache/` (git-ignored).

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
- **surf forecast** — pick a break on tab 1, then press **Get forecast**
  on tab 2. Skill defaults to the break's own `skillLevel`
  (`pro-only` → `expert`); days slider 1–7. Shows best-window hero,
  score curve, component breakdown, waves + wind charts, daily-best and
  hourly tables. See `documents/FORECAST.md`.

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

`main.py fetch_forecast` → `app/surf_forecast.get_scored_week`
(break → `adapters.enriched_to_scoring_spot` → `forecasts.get_forecast`
→ `scoring.score_week`) → Plotly figs + tables. Wind tolerance is a
flat `15kt` (`adapters.DEFAULT_WIND_MAX_KT`) because the schema carries
no wind-strength number. Full detail in `documents/FORECAST.md`.

## Kept for later

`wavereader/agent.py` / `wavereader/tools.py` are the agentic
forecast-explanation layer. Not wired into the UI yet — the forecast
tab is deterministic only by design.
