# Data generation — what it does and why

This folder contains the pipeline that produces the dataset used by
wavereader: a list of Australian surf breaks and a structured, web-grounded
profile of each one.

## Files

| File | Purpose |
| --- | --- |
| `breaks.json` | Input: the 100 surf breaks to describe (name + Australian state/region). |
| `generate_data.py` | The generator script. |
| `break_details.json` | Output: one structured record per break. Regenerated/resumable — safe to delete and re-run. |

## What the script does

For each break in `breaks.json`, `generate_data.py` makes a **two-phase** call
to an open-source LLM hosted on Hugging Face's inference router:

1. **Search phase.** The model is given a `web_search` tool (backed by
   DuckDuckGo) and asked to research the break. The first search is forced;
   after that the model decides whether more searches are worth it (up to 3
   rounds). The result is a bundle of search notes.
2. **Structured phase.** The notes are fed back to the model together with a
   one-shot example, and it must answer in JSON that strictly conforms to
   `SURF_BREAK_SCHEMA` (coordinates, ideal swell/wind/tide, break type,
   direction, bottom, skill level, season, hazards, notes).

Results are appended to `break_details.json` after every break, so an
interrupted run never loses completed work.

Usage:

```sh
uv sync            # install dependencies
hf auth login      # or: export HF_TOKEN="hf_xxx"
uv run data/generate_data.py
```

## Design decisions

### Model: `Qwen/Qwen3-Next-80B-A3B-Instruct`

The pipeline needs **one model that supports both OpenAI-style tool calling
and `json_schema` response format** on the HF inference router. This
combination rules out most candidates — we tested before committing:

- `mistralai/Mistral-7B-Instruct-v0.3` — rejected by the router ("not a chat
  model"); this was the original model in the script and the reason the first
  run failed on every break.
- `meta-llama/Llama-3.1-8B-Instruct` — tool calling works, but strict
  `json_schema` returns a 405 from the router.
- `Qwen/Qwen3-4B-Instruct-2507` — the reverse: JSON schema works, forced tool
  calls are rejected.
- `Qwen/Qwen3-Next-80B-A3B-Instruct` — supports both, and being a mixture-of-
  experts model (80B total, ~3B active parameters) it is much faster and
  cheaper per call than a dense model of similar output quality.

If this model ever disappears from the router, re-test candidates with both
features before swapping the `MODEL` constant.

### Two phases instead of one tool-using call

`json_schema` response format and tool calling cannot be combined in a single
request, so the research and the structured answer are separate steps. This
also works in the pipeline's favour: the search phase can produce free-form
notes (the model's own summary of what it found), and the final phase can be
tightly constrained without forcing the model to emit JSON mid-tool-loop.

### Web search grounding at all

The model's training data can be stale or thin on obscure spots (e.g. "Cactus
Beach - Point Sinclair", "Pondalowie Bay"), and details like access, hazards
and contest history benefit from current sources. DuckDuckGo was chosen
because it is free and needs no API key. The first search is **forced**
(`tool_choice` pinned to `web_search`) because the model otherwise tends to
answer from memory; after that it may stop searching.

### Strict JSON schema output

The output is consumed programmatically downstream, so parsing is not
optional and free-form JSON parsing is fragile (code fences, prose around the
object, truncated output). `response_format` with `json_schema` + `strict:
true` makes the router constrain generation, so in practice every response
parses. The schema uses `additionalProperties: false` everywhere so the
records are uniform. A one-shot example (Bells Beach) is included to set the
expected level of detail and tone of the free-text fields.

### Identity fields anchored to the input

The model sometimes renames multi-name spots — "Cronulla - Voodoo" came back
as "Voodoo", "Rottnest Island - Strickland Bay" as "Strickland Bay". Since
records are matched to `breaks.json` by name+region downstream, the script
overwrites the returned `name`/`region` with the input values. (The first
full run produced 12 such renames; the content itself was accurate.)

### Resume + retry in the batch runner

A 100-break run takes ~20 minutes and each break involves several network
calls, so transient failures (rate limits, timeouts) are expected. The runner:

- keys results by `(name, region)` and skips entries already present without
  an `error` field — re-running only does missing/failed breaks;
- retries each break up to 2 attempts with backoff;
- writes the output file after every break, so a crash mid-run loses nothing;
- leaves a `{"name", "region", "error"}` record for permanent failures rather
  than dropping the break, making gaps visible.

### Auth

The script uses the locally stored Hugging Face token from `hf auth login`,
with the `HF_TOKEN` environment variable as an explicit override. It does not
require the env var, which was another reason the original version failed out
of the box.

### `ddgs` instead of `duckduckgo-search`

`duckduckgo-search` is the deprecated package name; `ddgs` is its successor
and is the dependency in `pyproject.toml`. The import has a fallback so both
installations work.

### Known limitations

- The `web_search` tool results are given to the model "for grounding", but
  the model is ultimately trusted to fill gaps with plausible estimates (the
  system prompt explicitly permits best estimates over fabrication). Values
  like ideal swell range are inherently judgment calls, not hard data.
- Coordinates are model estimates; good enough for map display, not surveyed
  positions.
- The whole dataset depends on a third-party inference router; re-running
  later may produce slightly different records (temperature is 0.2 to keep
  runs stable, not identical).
