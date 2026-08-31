# wave~reader

**An agentic surf forecaster for Australian breaks — built for the [NVIDIA GTC Berlin Golden Ticket contest](https://developer.nvidia.com/gtc-golden-ticket-contest).**

Surf forecasting runs on inherent knowledge: which winds suit which break, what swell size a spot can handle, which tide is working. WaveReader encodes that knowledge for 101 Australian breaks and puts an open-model agent on top of live marine data, so anyone can just ask:

- _"Which days are good to surf this week near Byron Bay, and where?"_
- _"What time should I surf Snapper Rocks tomorrow? I ride a mid-length."_

The agent calls real forecast tools, scores every spot with a deterministic surf-quality engine, and **explains** the answer — it never invents the numbers.

> 🎬 Built Aug 30 – Sep 7, 2026. Live demo on Hugging Face Spaces: _(link on launch day)_

## Features

|                                    |                                                                                                                                                                                |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 🤖 **Agentic answers**             | smolagents CodeAgent over Qwen3-Next-80B — the LLM interprets, deterministic tools own the data.                                                       |
| 📊 **Interactive forecast graphs** | Whenever the agent surfaces wind, swell or wave data, it renders as interactive charts (seaborn-styled): hourly wave height, period, wind speed and direction.                 |
| 🗺️ **Australia break map**         | The home page is a map of Australia: pick your break directly, or search by city/suburb and let the agent rank nearby spots for your skill level.                              |
| 🧠 **Break knowledge base**        | 101 breaks with coordinates, ideal swell/wind/tide, break type, skill level and hazards — generated with an open model, web-grounded, published as an open dataset.            |
| 🎛️ **Visible reasoning**           | Every tool call (name, arguments, latency, result) appears in a trace panel; a **daggr "Morning Surf Report" canvas** shows the whole pipeline as an inspectable visual graph. |
| 🔀 **Dual model hosting**          | One OpenAI-compatible client, switchable at runtime between **Hugging Face Inference** and **NVIDIA NIM** — same open model, two hosts.                                        |

## Architecture

```
┌────────────────────────────  UI (Gradio)  ────────────────────────────┐
│  Australia break map · chat · interactive forecast charts · trace panel│
│  daggr canvas: "Morning Surf Report" pipeline                          │
└──────────────────────────────┬────────────────────────────────────────┘
                               │
┌──────────────────────────────▼─────────────  FastAPI  ────────────────┐
│  /spots  /forecast  /score  /ask                                      │
├───────────────────────────────────────────────────────────────────────┤
│  agent.py — smolagents CodeAgent (streaming + trace)                   │
│      ↳ tools: get_forecast · score_week · find_spots(near/skill)       │
│               get_spot_knowledge · rank_spots_this_week                │
├───────────────────────────────────────────────────────────────────────┤
│  scoring.py — deterministic 0–10 surf-quality score per hour:          │
│    swell size vs ideal range · swell direction match · wind speed +    │
│    offshore alignment · wave period → per-component breakdown          │
├───────────────────────────────────────────────────────────────────────┤
│  forecasts.py — Open-Meteo Marine API (hourly wave height/period/      │
│    direction, swell, wind; 7-day horizon, cached)                      │
│  spots.py — 101-break knowledge base (data/break_details.json)         │
├───────────────────────────────────────────────────────────────────────┤
│  LLM: Qwen/Qwen3-Next-80B-A3B-Instruct                                 │
│    via HF Inference Providers  ⇄  NVIDIA NIM (env-switchable)          │
└───────────────────────────────────────────────────────────────────────┘
```

**Design principle:** the model orchestrates; it doesn't hallucinate. Forecast numbers, scores and rankings all come from code and APIs — the agent's job is interpretation, explanation and recommendation.

## The data

`data/break_details.json` holds one record per break: coordinates, ideal swell (size range + direction), ideal wind (max strength + offshore direction), ideal tide, break type/direction/bottom, skill level, best season, hazards and notes — for breaks across NSW, QLD, VIC, WA, SA and TAS. How it's generated and why it's built this way:
[data/GENERATION.md](data/GENERATION.md).

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

For the data generation script, authenticate with Hugging Face (token is
stored locally and picked up automatically):

```sh
hf auth login
# or: export HF_TOKEN="hf_xxx"
```

## Generate surf break data

Reads `data/breaks.json` and writes grounded details for each break to
`data/break_details.json`. The run is resumable — already-fetched breaks are
skipped, failed ones are retried.

```sh
uv run data/generate_data.py
```

## Run the app

API server (OpenAPI docs at `/docs`):

```sh
uv run uvicorn wavereader.api:app --reload
```

Gradio UI:

```sh
uv run python -m wavereader.app
```

Legacy dev server:

```sh
uv run fastapi dev main.py
```

## Built with open everything

- **Model:** Qwen3-Next-80B (open weights) — served by Hugging Face Inference Providers and NVIDIA NIM
- **Workflow canvas:** [daggr](https://github.com/gradio-app/daggr) (the Gradio team's visual AI-workflow library)
- **Forecasts:** [Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api) (free, no key)
- **Knowledge base:** open dataset, built with an open model

## Context

Built as an entry for the **NVIDIA GTC Berlin Golden Ticket contest** (free GTC Berlin pass, Oct 20–22, 2026; submissions close Sep 10, 2026) — and by a data scientist who just moved to Berlin, 16,000 km from the nearest surf break. 🐻

_Say hi if you're working on LLM agents or applied ML in Berlin — DMs open._
