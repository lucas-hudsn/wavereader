"""
Hugging Face Inference Providers + NVIDIA Nemotron 3 -- surf break generator
Notes:
- This is a single-shot structured-JSON-generation task, NOT an agentic
  tool-use task, so we call the model directly via huggingface_hub's
  InferenceClient.chat.completions.create() rather than wrapping it in a
  smolagents CodeAgent. CodeAgent runs a ReAct loop that expects the model
  to respond with Python code inside <code>...</code> tags and finish by
  calling final_answer(...) -- that format directly conflicts with our
  prompt's instruction to output raw JSON with "no markdown fences, no
  commentary," which is why CodeAgent kept failing to parse the model's
  (correct) JSON output as code.
- `provider` selects which Hugging Face Inference Provider serves the model
  (e.g. "novita", "nebius", "together", "fireworks-ai", "sambanova", etc.) --
  check the model page on huggingface.co for which providers currently host it.
- Model used: nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16, the current
  flagship of NVIDIA's Nemotron 3 family (Nano / Super / Ultra), released 2026.
  Swap in a lighter sibling if you want lower latency/cost.

Prompt data lives in ./data/ instead of being embedded in this file:
    data/schema.json         - the JSON Schema the output must conform to
    data/example_output.json - the worked example's expected output JSON 

Requires:
    uv add huggingface_hub
    export HF_TOKEN=your_hf_token   # needs Inference Providers access
"""
import json
import os
import re
import sys
from pathlib import Path

from huggingface_hub import InferenceClient

DATA_DIR = Path(__file__).parent.parent / "data"

MODEL_ID = "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16"
PROVIDER = "deepinfra"


def load_prompt_parts(data_dir: Path = DATA_DIR) -> dict:
    """Load the instructions, schema, and worked example from data/."""

    schema_obj = json.loads((data_dir / "surf-break-schema.json").read_text())
    schema_str = json.dumps(schema_obj, indent=2)

    example_input = "Bells Beach, Surf Coast, Victoria"

    example_output_obj = json.loads((data_dir / "surf-break-example-bells.json").read_text())
    example_output_str = json.dumps(example_output_obj, indent=2)

    return {
        "schema": schema_str,
        "example_input": example_input,
        "example_output": example_output_str,
    }


def build_surf_break_prompt(break_name: str, state: str = "", region: str = "", data_dir: Path = DATA_DIR) -> str:
    """Assemble the full generator prompt from the data/ files plus the new break to generate."""
    parts = load_prompt_parts(data_dir)

    target_break = f"{break_name}, {state}, {region}"

    return f"""
You are a surf break data generator. You will be given a JSON Schema describing a surf break, one fully worked example that conforms to it, and then a new break to generate.

Follow these rules:
1. Output only valid JSON conforming to the schema below - no markdown fences, no commentary, no trailing notes.
2. Populate every "required" field. Fill in optional fields whenever you have reasonable real-world knowledge to support them; omit an optional field entirely rather than guessing wildly or inserting null/placeholder values.
3. Use only the allowed enum values exactly as spelled in the schema - do not invent new enum values.
4. Base swell direction, wind direction, tide behavior, seasonality, and hazards on the break's actual real-world geography and known surf reports, not generic defaults.
5. Coordinates should be your best real-world estimate for the actual break, not the nearest town center, where you can distinguish them.
6. If a break has well-known sub-sections (e.g., a reef with multiple named peaks), describe the primary/main takeoff zone unless told otherwise.
 7. Keep "description" to 2-4 sentences: character of the wave, what it's known for, any standout feature.
 8. Copy the state and region from the "Input break" verbatim into the top-level
    "state" / "region" fields AND into "location.state" / "location.region" --
    do not expand, abbreviate, or combine them (e.g. input "Victoria / Surf Coast"
    must give "state": "Victoria", "region": "Surf Coast",
    "location": {{"region": "Surf Coast", "state": "Victoria", ...}}).

### JSON Schema

```json
{parts['schema']}
```

### Worked Example (Input -> Output)

Input break: {parts['example_input']}

Output:

```json
{parts['example_output']}
```

### Now generate the following break

Input break: {target_break}

Output:
"""


def extract_json(text: str) -> dict:
    """Pull a JSON object out of the model's reply, tolerating stray code fences."""
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ``` fences if the model added them anyway.
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        # Fall back to grabbing the outermost { ... } block.
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0)
    return json.loads(text)


def generate_surf_break(
    break_name: str,
    state: str = "",
    region: str = "",
    model_id: str = MODEL_ID,
    provider: str = PROVIDER,
    max_tokens: int = 2048,
    temperature: float = 0.4,
) -> dict:
    """Generate one schema-valid surf break JSON object via a single chat completion call."""
    hf_token = os.environ.get("HF_TOKEN")


    client = InferenceClient(provider=provider, api_key=hf_token)

    prompt = build_surf_break_prompt(break_name, state, region)

    completion = client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )

    raw_text = completion.choices[0].message.content
    return extract_json(raw_text)



if __name__ == "__main__":

    break_name = sys.argv[1] if len(sys.argv) > 1 else "Kilcunda"
    state = sys.argv[2] if len(sys.argv) > 2 else "Victoria"
    region = sys.argv[3] if len(sys.argv) > 3 else "Bass Coast"

    prompt = build_surf_break_prompt(break_name, state, region)

    result = generate_surf_break(break_name, state, region)
    print(result)
