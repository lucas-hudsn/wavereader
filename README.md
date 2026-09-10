# wave~reader

**A surf-forecasting world model for the Australian coast: 238 breaks, 168
deterministic scores per spot, a 3D seafloor built from real GEBCO
bathymetry — and one open model that narrates the numbers instead of
inventing them.**

wave~reader is a single-page Gradio app, built in September 2026
as an entry for the **GTC Berlin Golden Ticket Developer Contest**. I have
just moved to Berlin; I wanted to build something to make me enjoy ML and
engineering again.

> [Built for GTC Berlin](#built-for-the-gtc-berlin-golden-ticket-developer-contest-) —
> NVIDIA open weights on Hugging Face rails. #NVIDIAGTC

## One rule holds the whole app together

**The LLM never owns numbers.** Every wave height, wind reading, and 0–10
score on screen comes out of plain, deterministic Python —
`wavereader/scoring.py`, `wavereader/openmeteo.py`, `wavereader/tools.py` —
running over Open-Meteo marine data and the enriched break catalogue. The
model's contract, written into its system prompt, is to interpret those
numbers, name the tool that produced them, and never compute a forecast
itself. The agent can _recommend_; it can't _hallucinate a swell_.

That split — a deterministic core with the model bolted on as an
interpreter — is the entire architecture, and it's what makes an
open-weights model safe to plan a surf trip around.

## One screen, four instruments

There are no tabs. One surface, four synchronized instruments, one source
of truth (`selected`): picking a spot re-aims everything at once.

| Instrument                  | What it does                                                                                                                                                                                                                                                                                                                                                                           |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Map lens** (left)         | All 238 breaks on a Plotly map, filtered by state / region / skill. A pick loads the full field guide and re-aims the forecast, world model, and climatology.                                                                                                                                                                                                                          |
| **Forecast story** (center) | The engines spin up in visible stages — status lines name the engine and its latency. You get a 0–10 score for every hour of the next 7 days, score / swell / wind strips with weekend shading, then a **smoothed 3D seafloor with an animated swell layer** riding the forecast's dominant period (press ▶ swell). An optional streamed narrator writes it up — from the scores only. |
| **Intel rail** (right)      | Field guide (peak type, ideal swell / wind / tide, hazards, crowd factor), a **5-year ERA5 swell climate rose** that audits the dataset's own claims, a wetsuit hint, and nearby surf cams.                                                                                                                                                                                            |
| **Agent bar** (full width)  | Chat: _"where's it going to be good in NSW this weekend?"_ A smolagents `ToolCallingAgent` on Nemotron 3 Ultra finds spots, ranks regions, explains score breakdowns, and suggests similar breaks. Every tool card shows its **latency in ms**; charts render mid-answer straight from tool payloads. Hard budget: 6 steps, 700 tokens a turn.                                         |

## Machinery you can watch

The app wears its internals on its sleeve: a strip across the top shows
every engine (🌍 world model · 📡 feeds · 🌡 climate · ⚙ scorer · 🧠 LLM ·
🔌 MCP) with live timings, and slow work loads in stages so the charts are
never blocked. Measured on a laptop against the disk cache:

| Engine                                       | Cold     | Warm       | Where                     |
| -------------------------------------------- | -------- | ---------- | ------------------------- |
| ⚙ scoring engine (168 hourly 0–10 scores)    | ~300 ms  | **0.8 ms** | `wavereader/scoring.py`   |
| 📡 Open-Meteo marine + wind feed             | ~300 ms  | **~1 ms**  | `wavereader/openmeteo.py` |
| 🌍 GEBCO world model (10×10 bathymetry grid) | ~1.3 s   | **~1 ms**  | `wavereader/seafloor.py`  |
| 🧠 agent tool call (`score_week` over MCP)   | ~2 ms    | **0.7 ms** | `wavereader/tools.py`     |
| Chart trio (score / swell / wind)            | 12–14 ms | —          | `ui/charts/`              |

Forecast charts land in ~80 ms while the world model resolves in a
parallel thread. `scripts/warm_caches.py` pre-fills every cache before a
demo, so a cold start never happens on camera. The seafloor view bicubically
upsamples the 10×10 GEBCO grid to 41×41 and animates a translucent swell
surface at the forecast's dominant height and period — a world model you
can watch working. (Smoothing and animation are display-only; statistics
always come from the raw grid.)

## The stack: NVIDIA open weights on Hugging Face rails

Every model call in the repo goes through one door — **Hugging Face
Inference Providers**, served by DeepInfra — running
[`nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16`](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16),
the open-weights Ultra of NVIDIA's Nemotron 3 family. No private APIs, no
proprietary endpoints, one `HF_TOKEN`. Around the model, everything is
open too: Open-Meteo forecasts, ERA5 reanalysis, GEBCO 2020 bathymetry via
OpenTopoData, and a scoring engine you can read in one sitting.

With NVIDIA and Hugging Face now one family, this app got to be an early
wedding photo. 🎉

## The app is the tool: MCP built in

`app.py` launches with `mcp_server=True`, so any MCP client (Claude
Desktop, opencode, …) can drive the deterministic engines directly at
`<space-or-local-url>/gradio_api/mcp/`. The public surface is exactly
three typed tools — the same functions the agent calls internally:

- `score_week` — hourly 0–10 scores, daily bests, best window for one break
- `rank_region_week` — every break in a region, ranked best-first
- `explain_score` — the size / direction / wind / period breakdown of one scored hour

Verify with `curl <url>/gradio_api/mcp/schema`. Everything else in the UI
is registered with `api_name=False` on purpose — the MCP surface stays
clean.

## Quickstart

Needs [uv](https://docs.astral.sh/uv/) and Python ≥ 3.14.

```sh
uv sync
cp .env.example .env   # fill in HF_TOKEN (https://huggingface.co/settings/tokens)
uv run app.py
```

Or skip the UI and drive the agent from Python:

```sh
uv run python -c "from wavereader.agent import run_stream; \
  [print(e.get('text', e.get('name', '')), end='') for e in run_stream('best beginner morning this weekend in VIC?')]"
```

`HF_TOKEN` is only needed for the agent and the narrator — the forecast
charts, world model, and MCP tools run token-free with plain network
access to Open-Meteo / OpenTopoData and a disk cache under `.cache/`.
On a HF Space the secret is the fallback; the agent panel's BYO-token box
is session-only and never logged.

## Deploying to HF Spaces

The app is live at [huggingface.co/spaces/lucashudsn/wavereader](https://huggingface.co/spaces/lucashudsn/wavereader).
The Space _is_ this git repo — the `space` remote points at it. Spaces
read their config from YAML frontmatter at the top of `README.md`, but
GitHub renders that block as an ugly metadata table, so it lives in
`space-config.yaml` instead and `deploy_space.sh` prepends it in a
throwaway commit at push time. Keep `sdk_version` in lockstep with the
gradio pin in `requirements.txt`. If you change Space settings through
the web UI, HF commits them into the Space's `README.md` — mirror
anything you care about back into `space-config.yaml`.

```sh
scripts/deploy_space.sh   # ship what's committed on v2 (pass a ref to override)
git push origin branch_name        # keep GitHub in sync
```

The push asks for credentials: username `lucashudsn`, password = an HF
token with write access (https://huggingface.co/settings/tokens). The
build takes a few minutes; watch it under the Space's _Logs → Build_ tab
or poll `HfApi().get_space_runtime("lucashudsn/wavereader")`.

Secrets live in the Space's _Settings → Variables and secrets_ —
`HF_TOKEN` is already set, which is what lets the agent and narrator work
for visitors. `WR_MODEL` / `WR_PROVIDER` / `WR_BASE_URL` can be added the
same way if you ever want to reroute the LLM. Caches under `.cache/` are
ephemeral on the Space and rebuild lazily after a restart; nothing else
needs doing.

## How it's laid out

```
app.py                           # HF Space entry: single-page UI + gr.api MCP tools
ui/                              # the front end
  app.py                         # layout + wiring (≤3 gr.State; Bells on load)
  panels/{lens,story,intel,agent}.py  # map lens | forecast story | intel rail | agent bar
  charts/{map,strip,score,seafloor,climate,_style}.py  # Plotly builders, one theme
  contracts.py                   # SELECT/FETCH/AGENT key contracts — no output-order drift
  _compat.py                     # backend access: v2 core → legacy.app.* → stubs
  theme.py                       # APP_CSS — IBM Plex Mono lo-fi identity
wavereader/                      # pure core: typed, tested, zero Gradio imports
  breaks.py openmeteo.py scoring.py seafloor.py climate.py
  tools.py                       # the deterministic tool functions (agent + MCP)
  agent.py                       # smolagents ToolCallingAgent, typed event stream
  narrate.py llm.py              # streamed report writer; one InferenceClient factory
scripts/
  warm_caches.py                 # demo hot start: forecast + seafloor caches
  build_climate.py               # ERA5 5-yr climatology builder (re-embeds catalogue)
  check_coords.py check_coast.py # coordinate + GEBCO coastline maintenance
  eval_agent.py                  # agent evaluation harness
data/
  australia-surf-breaks-enriched.json  # 238 schema-valid breaks, ERA5 embedded
  surf-break-schema.json               # the conformance contract
  surf-break-example-bells.json        # prompt worked example
  surf-cams.json                       # camera links keyed name | state | region
documents/
  ENCYCLOPEDIA.md FORECAST.md SURFAGENT.md
legacy/                          # frozen v1 front end, kept as the compat fallback
```

Cheap checks: `uv run pytest -q` (offline fixtures, including an agent
dry-run through an injected fake model) and `uv run python -c "import app"`.

## Where the data came from

The break catalogue was generated by running **Nemotron 3.5 Lightning**
once per break through the v1 pipeline (now archived in `legacy/`): one
chat call per spot at temperature 0.4, with the JSON schema and the Bells
Beach worked example loaded from `data/` into the prompt.
`state` / `region` are pinned from the input list, never taken from the
model, and every record validates against
`data/surf-break-schema.json` with strict enums for swell, wind, tide,
skill, and hazards. The batch runner is resumable.

After the build, `scripts/build_climate.py` gave each break a **5-year
ERA5 swell profile** (embedded in the record itself — 236 of 238; two
duplicate Gnaraloo rows miss out) and `scripts/check_coords.py` /
`scripts/check_coast.py` keep coordinates honest against OSM and the GEBCO
shoreline. The climate rose in the intel rail uses those profiles to audit
the dataset: where the model's claimed "ideal swell" disagrees with five
years of observed reanalysis, the data wins.

## The forecast pipeline, end to end

1. **Deterministic core.** break → `scoring.py` →
   `openmeteo.get_forecast` (Open-Meteo marine + wind, disk-cached,
   snapped seaward to the right grid cell) → `score_week` → 168 hourly
   scores → Plotly strips + best-window hero. In parallel, the **world
   model** pulls the GEBCO 2020 grid around the takeoff zone, classifies
   the shelf shape, and renders depth, 3D, and transects with the
   animated swell layer.
2. **Narrator (optional).** The prompt carries only the daily bests
   (≤7 lines) plus the best window; Nemotron 3 Ultra streams a dot-point
   write-up of exactly those numbers. Nothing more.

Full detail in [`documents/FORECAST.md`](documents/FORECAST.md).

## Built for the GTC Berlin Golden Ticket Developer Contest 🎟️

wave~reader is a contest entry: an app that could only exist because
NVIDIA ships frontier-class open weights and Hugging Face turns them into
one-token inference. It leans on both halves deliberately — Nemotron 3
Ultra for language, deterministic Python for physics — and shows its work
on screen the whole way.

Tagging @Merve Noyan — thanks for the nudge. #NVIDIAGTC
