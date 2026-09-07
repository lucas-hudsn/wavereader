# wave~reader

Australian surf-break encyclopaedia + agentic forecaster (work in progress).

The current front end is a Gradio map UI (`main.py`). Break knowledge is
generated as schema-valid JSON by the scripts in `app/` using an NVIDIA
model via Hugging Face Inference Providers. The deterministic
forecast/score/agent code in `wavereader/` is kept and will be reimplemented
against the new schemas + UI.

## Layout

```
main.py                          # Gradio map front end (run this)
app/
  generate_surf_break.py         # single-shot structured-JSON break generator
  generate_base_data.py          # batch/resumable enrichment runner
data/
  australia-surf-breaks.json           # input: nested state -> region -> [names]
  australia-surf-breaks-enriched.json  # output: list of schema-valid breaks
  surf-break-schema.json               # JSON Schema every break must conform to
  surf-break-example-bells.json        # worked example (Bells Beach) used in the prompt
wavereader/
  agent.py / tools.py / forecasts.py / scoring.py   # kept, to reimplement
```

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14 (`uv sync` reads
`.python-version`).

```sh
uv sync
cp .env.example .env   # then fill in HF_TOKEN
```

`HF_TOKEN` needs Inference Providers access:
https://huggingface.co/settings/tokens

## Run the front end

```sh
uv run python main.py
```

Opens a Gradio app:

- State / Region / Skill filters reframe a Plotly `Scattermap` of Australia.
- Hover a dot for name + region + skill; pick a break for its details table.
- "Can't find your local break?" generates one live via
  `app/generate_surf_break.py` — session-only (kept in `gr.State`, never
  written to `data/`). Generating again replaces it; "Delete my break"
  removes it.

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

## Kept for reimplementation

`wavereader/agent.py`, `wavereader/tools.py`, `wavereader/forecasts.py`,
`wavereader/scoring.py` are the old deterministic forecast/score/agent
functions and tools. They still reference the previous data layout and are
kept as-is to be rewired to the new schemas and the `main.py` front end.
