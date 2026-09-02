# Architecture

How wavereader turns a natural-language question into a grounded surf
recommendation. The one-sentence version: **the LLM orchestrates, code owns
the numbers.**

```
question ──▶ SurfAgent (smolagents CodeAgent, Qwen3-Next-80B)
                │  writes python code that calls tools
                ▼
             tools.py ──▶ spots.py (knowledge base)
                │        forecasts.py (Open-Meteo + disk cache)
                │        scoring.py (deterministic 0–10 score)
                ▼
        streaming answer + AgentTrace ──▶ Gradio UI (trace panel + auto-charts)
```

## Modules

| Module | Role | Key facts |
|---|---|---|
| `spots.py` | Loads + validates `data/breaks.json` / `break_details.json`; search | Records keyed by `(name, region)`; coords validated against per-state bounding boxes; 6 regions (NSW, QLD, VIC, WA, SA, TAS) |
| `forecasts.py` | Open-Meteo Marine + weather client | Hourly, 7-day horizon; merges two endpoints on `time`; disk cache with stale fallback (below) |
| `scoring.py` | Deterministic surf-quality score | Pure functions, no I/O; per-hour 0–10 score + component breakdown (below) |
| `agent.py` | smolagents CodeAgent wrapper | `SurfAgent`, provider switching, streaming, `AgentTrace`; `max_steps=10` |
| `tools.py` | Agent tools + matplotlib plot builders | 5 core tools; plain functions resolve spot by `(name, region)` then delegate |
| `api.py` | FastAPI backend | `/spots`, `/forecast`, `/score`, `/ask` — see [API.md](API.md) |
| `app.py` | Gradio UI | Map-first layout, streaming chat, trace panel, auto-charts — see [UI_GUIDE.md](UI_GUIDE.md) |
| `daggr_pipeline.py` | Fixed Morning Surf Report DAG | Visualises the deterministic pipeline only, **never** the dynamic chat loop (daggr beta has no conditional branching) |

## The model boundary

`SYSTEM_PROMPT` in `agent.py` enforces the product's core rule: the agent
never computes a number. It writes code that calls tools, reads the results,
and explains them. Everything numeric comes from:

- **Forecasts** — Open-Meteo responses, normalised to hourly rows
  (`time`, `wave_height`, `wave_period`, `wave_direction`, `wind_speed_10m`,
  `wind_direction_10m`).
- **Scores** — `scoring.score_hour()`, weighted:
  swell_size 0.30 · swell_direction 0.20 · wind 0.30 · period 0.20.

Component logic (all continuous curves, no cliff edges):

- **Swell size** — 10 inside the spot's ideal `size_ft_min–max` window,
  Gaussian decay outside, zero above the skill profile's `max_safe_size_ft`.
- **Swell direction** — Gaussian on angular distance from the spot's ideal
  direction (45° tolerance); `None` when Open-Meteo has no wave direction,
  and its weight is redistributed across the remaining components (never
  silently substituted with wind direction).
- **Wind** — mean of a speed score and a direction score. Speed: glassy
  (≤ 5 kt) is always 10, above `min(spot max, skill max)` it is 0.
  Direction: cosine falloff from perfect offshore to absolute onshore.
- **Period** — linear ramp, 0 at ≤ 4 s up to 10 at ≥ 14 s; long groundswell
  is never penalised.

Skill profiles (`beginner / intermediate / advanced / expert`) cap wave size,
wind tolerance and set the comfort band. Every scored row carries its raw
inputs back (`wave_height_m`, `wind_speed_kt`, …) so the UI and trace can
show *why* a score is what it is.

## Forecast fetching and the demo-survivability cache

- Grid points sit offshore: coords are snapped **0.13° seaward** — Tasmania
  and the south coast shift south, the east coast (lon ≥ 147) shifts east,
  the west coast (lon ≤ 125) shifts west.
- Responses are cached to disk at `.cache/forecasts/{lat}_{lon}_{days}.json`
  as `{"fetched_at": ..., "data": ...}` envelopes, TTL **6 hours**.
- On a network failure the most recent entry — however stale — is served
  instead of raising; the app only errors when there is no data at all. This
  is deliberate: the demo video must survive API flakiness and rate limits.
- On UI startup a background thread warms the cache for all 100 breaks
  (disable with `WAVEREADER_WARM_CACHE=0`).

## Agent ↔ UI contract

`SurfAgent.run_stream(question)` yields:

- `("model", delta)` — LLM token chunks (the agent's code-as-reasoning)
- `("tool", tool_name)` — a tool call is happening
- `("final", answer)` — the clean final answer

Every run also fills an `AgentTrace` (`trace.to_json()`), with event types
`tool_call` / `tool_result` / `llm_chunk` / `final_answer`. The UI renders
this JSON in the trace panel and scrapes the code steps for
`get_forecast` / `score_week` / `get_spot_knowledge` /
`rank_spots_this_week(...)` invocations — whichever spots the agent touched
get interactive plotly charts rendered beneath the chat. Charts are drawn by
the UI, never by the agent, so the model's context stays small and the
graphics stay interactive.

Note for tool-call tracing: smolagents CodeAgents emit one
`python_interpreter` call per step whose "arguments" are the generated code
blob — the trace panel detects real tool usage inside the blob by regex.

## Provider switching

Both hosts speak the OpenAI chat-completions protocol, so one client class
(smolagents `OpenAIServerModel`) covers the switch:

| Provider | Base URL | Env var |
|---|---|---|
| `hf` (default) | `https://router.huggingface.co/v1` | `HF_TOKEN` |
| `nim` | `https://integrate.api.nvidia.com/v1` | `NVIDIA_API_KEY` |

When both tokens are set, NIM wins auto-detection; the UI exposes an explicit
radio switch. `Qwen/Qwen3-Next-80B-A3B-Instruct` is the only model verified
for both OpenAI-style tool calling and strict `json_schema` on the HF router
— read `data/GENERATION.md` before swapping models.

## Testing

`uv run pytest` (134 tests) covers scoring curves, cache behaviour/offsets,
spot validation, tool wiring, the agent (mocked model), the API, the daggr
pipeline and the UI chart builders. The agent tests mock the LLM, so the
suite runs offline; the forecast tests mock HTTP but exercise the real cache
code paths via `tmp_path`.
