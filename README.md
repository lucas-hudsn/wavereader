# wave~reader

**238 Australian surf breaks, a deterministic 7-day swell score, and a surf
agent that talks to you — all powered by open models on Hugging Face
Inference Providers.**

> Built in a week, in September 2026, from a fresh pair of shoes: I'd just
> moved to Berlin, I'm on a careers break, and I needed a project that was
> about waves before it was about weights. 🌊

## The stack: Hugging Face × NVIDIA

Every model call in this repo goes through one door: **Hugging Face
Inference Providers** (served by Fireworks AI), running
[`nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16`](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16)
— the open-weights Lightning model of NVIDIA's Nemotron 3 family. No private APIs,
no proprietary models, one `HF_TOKEN`.

So wave~reader is, at its core, a love letter to open models on
first-party infra: **NVIDIA's open weights, Hugging Face's inference
fabric, open data (Open-Meteo), and a deterministic Python scoring engine
in the middle that the LLM is contractually forbidden to touch.**

Big congrats to Hugging Face on the NVIDIA acquisition 🎉 — the two halves
of this stack just became one family, and this app got to be an early
marriage photo.

## What it does

Three experiences in one Gradio app (`uv run python app.py`):

| Tab / mode | What you get |
|---|---|
| **break book** | All 238 breaks on a Plotly map, filterable by state / region / skill. Each pick loads a full field guide (peak type, ideal swell / wind / tide, hazards, crowd factor) plus a **5-year ERA5 swell climate rose** that audits the dataset's own claims. |
| **swell check** | Pick a break → the deterministic engines spin up in stages: **📡 Open-Meteo feed → ⚙ scoring engine → 🌍 GEBCO world model**, each with live timings. 0–10 score for every hour of the next 7 days, score/swell/wind strips, and a **smoothed 3D seafloor model with an animated swell layer** riding the forecast's dominant period (press ▶ swell). Then an optional streamed AI write-up that *narrates the scores only*. |
| **surf agent** | Chat: "where's it going to be good in NSW this weekend?" — a smolagents `ToolCallingAgent` on Nemotron 3.5 Lightning that finds spots, scores regions, explains score breakdowns, ranks the week, and suggests similar breaks. Every tool call shows its **latency in ms**; charts render mid-answer straight from the tool payloads. |

## The engines — and why the spin-ups are fast

wave~reader makes its machinery visible. Measured on a laptop against the
disk cache:

| Engine | Cold | Warm | Where |
|---|---|---|---|
| ⚙ scoring engine (168 hourly 0–10 scores) | ~300 ms | **0.8 ms** | `wavereader/scoring.py` |
| 📡 Open-Meteo marine + wind feed | ~300 ms | **~1 ms** | `wavereader/openmeteo.py` |
| 🌍 GEBCO world model (10×10 bathymetry grid) | ~1.3 s | **~1 ms** | `wavereader/seafloor.py` |
| 🧠 agent tool call (`score_week` over MCP) | ~2 ms | **0.7 ms** | `wavereader/tools.py` |
| Chart trio (score / swell / wind) | 12–14 ms | — | `ui/charts/` |

The forecast charts land in ~80 ms while the world model resolves in a
parallel thread; caches warm themselves on load (`scripts/warm_caches.py`
pre-fills them before a demo recording). The seafloor view bicubically
upsamples the 10×10 GEBCO grid to 41×41 and animates a translucent swell
surface at the forecast's dominant height/period — a world model you can
watch working.

## The rule that makes it trustworthy

**The LLM never owns numbers.** Every wave height, wind speed, and score in
the UI comes from `wavereader/scoring.py` / `wavereader/openmeteo.py` /
`wavereader/tools.py`
— plain Python over Open-Meteo + the enriched break dataset. The model's
contract (enforced by its system prompt) is to interpret, cite the tool it
used, and never compute a forecast itself. The agent can *recommend*, but it
can't *hallucinate a swell*.

That split — deterministic core, model as interpreter — is the whole
architecture, and it's what makes an open 30B model usable for something
you'd actually plan a surf trip around.

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14.

```sh
uv sync
cp .env.example .env   # fill in HF_TOKEN (https://huggingface.co/settings/tokens)
uv run python app.py
```

Or drive the agent straight from Python:

```sh
uv run python -c "from wavereader.agent import run_stream; \
  [print(e.get('text', e.get('name', '')), end='') for e in run_stream('best beginner morning this weekend in VIC?')]"
```

`HF_TOKEN` (Inference Providers access) is needed for the agent and the
narrator. The forecast charts, world model, and MCP tools run with no
token and no LLM — network access to Open-Meteo / OpenTopoData, with a
disk cache under `.cache/`.

## MCP: the app is the tool

`app.py` launches with `mcp_server=True`, so any MCP client (Claude
Desktop, opencode, …) can call the deterministic engines directly:

```
<space-or-local-url>/gradio_api/mcp/
```

The exposed surface is exactly three typed, deterministic tools —
`score_week`, `rank_region_week`, `explain_score` — the same functions the
agent calls. Verify: `curl <url>/gradio_api/mcp/schema`.

## Layout

```
app.py                           # v2 entry: Gradio 6 three-panel UI + MCP server
ui/                              # the front end
  app.py                         # layout + event wiring (engines strip, cache warm-up)
  panels/{book,swell,agent}.py   # break book / swell check / surf agent
  charts/{score,swell,wind,seafloor,climate,map}.py   # Plotly builders
  _compat.py                     # backend access layer (v2 core → legacy → stubs)
wavereader/                      # pure core: typed, tested, no Gradio imports
  breaks.py openmeteo.py climate.py scoring.py seafloor.py
  tools.py                       # the deterministic tool functions (agent + MCP)
  agent.py                       # smolagents ToolCallingAgent + typed event stream
  narrate.py llm.py              # streamed report writer; one InferenceClient factory
scripts/
  warm_caches.py                 # pre-fill forecast + seafloor caches (demo hot start)
  build_climate.py               # ERA5 5-yr climatology builder
data/
  australia-surf-breaks-enriched.json  # 238 schema-valid breaks
  climate/*.json                       # per-break 5-yr swell climatology
  surf-break-schema.json               # the conformance contract
documents/
  ENCYCLOPEDIA.md FORECAST.md SURFAGENT.md VIDEO_SCRIPT.md
legacy/                          # v1 front end (main.py + app/), archived
```

## How the dataset was built

`scripts/` (v1 generation pipeline in `legacy/app/`) ran Nemotron 3.5
Lightning once per break (temp 0.4, 2048 tokens, one chat call): the
prompt carries the JSON schema + the Bells Beach worked example, and
`extract_json()` strips fences / grabs the outermost `{...}`. Canonical
`state` / `region` are pinned from the input list, never the model, and
every record conforms to `data/surf-break-schema.json` (strict enums for
swell, wind, tide, skill, hazards…). The batch runner is resumable.

## The forecast pipeline

1. **Deterministic core:** break → `wavereader/scoring.py` →
   `openmeteo.get_forecast` (Open-Meteo marine + wind, disk-cached,
   seaward grid-snap) → `score_week` → 168 hourly 0–10 scores →
   Plotly score / swell / wind strips + best-window hero. The **world
   model** fetches the GEBCO 2020 bathymetry grid around the takeoff
   zone, classifies shelf shape, and renders depth / 3D / transects with
   an animated swell layer.
2. **LLM narrator (optional):** the prompt carries only the daily bests
   (≤7 lines) + best window; Nemotron 3.5 Lightning streams a dot-point
   write-up. It can only talk about the numbers it was handed.

Full detail in `documents/FORECAST.md`.

## Built for the GTC Berlin Golden Ticket Developer Contest 🎟️

Entry video script: `documents/VIDEO_SCRIPT.md`. Tagging @Merve Noyan —
thanks for the nudge. #NVIDIAGTC
