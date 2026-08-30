"""Generate structured details for every surf break in breaks.json.

For each break, an LLM hosted on Hugging Face researches it via a
DuckDuckGo web search tool, then returns details (coordinates, ideal
swell/wind/tide, break type, hazards, ...) as strict JSON. Results are
written to break_details.json. See GENERATION.md for design decisions.
"""

import json
import os
import textwrap
import time

from ddgs import DDGS
from huggingface_hub import InferenceClient

MODEL = "Qwen/Qwen3-Next-80B-A3B-Instruct"
INPUT_PATH = "data/breaks.json"
OUTPUT_PATH = "data/break_details.json"

MAX_SEARCH_ROUNDS = 3
MAX_ATTEMPTS = 2
TEMPERATURE = 0.2

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current, real-world info about a surf break "
            "(swell, wind, tide, hazards, season, access, etc)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
            },
            "required": ["query"],
        },
    },
}

SURF_BREAK_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "region": {"type": "string"},
        "short_description": {"type": "string"},
        "coordinates": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lng": {"type": "number"},
            },
            "required": ["lat", "lng"],
            "additionalProperties": False,
        },
        "ideal_swell": {
            "type": "object",
            "properties": {
                "size_ft_min": {"type": "number"},
                "size_ft_max": {"type": "number"},
                "direction": {"type": "string", "description": "e.g. 'SW', 'NW'"},
            },
            "required": ["size_ft_min", "size_ft_max", "direction"],
            "additionalProperties": False,
        },
        "ideal_wind": {
            "type": "object",
            "properties": {
                "strength_kt_max": {"type": "number"},
                "direction": {"type": "string", "description": "e.g. 'E', 'light and variable'"},
            },
            "required": ["strength_kt_max", "direction"],
            "additionalProperties": False,
        },
        "ideal_tide": {"type": "string", "description": "e.g. 'mid to high, rising'"},
        "additional_details": {
            "type": "object",
            "properties": {
                "break_type": {"type": "string", "description": "reef, point, beach break, etc."},
                "break_direction": {"type": "string", "description": "'left', 'right', or 'a-frame' (both)"},
                "break_surface": {"type": "string", "description": "'reef' or 'sand'"},
                "bottom_type": {"type": "string", "description": "e.g. 'coral reef', 'rock ledge', 'sand bar'"},
                "skill_level": {"type": "string"},
                "best_season": {"type": "string"},
                "hazards": {"type": "string"},
                "other_notes": {"type": "string", "description": "crowd factor, access, localism, etc."},
            },
            "required": [
                "break_type", "break_direction", "break_surface", "bottom_type",
                "skill_level", "best_season", "hazards", "other_notes",
            ],
            "additionalProperties": False,
        },
    },
    "required": [
        "name", "region", "short_description", "coordinates",
        "ideal_swell", "ideal_wind", "ideal_tide", "additional_details",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = textwrap.dedent("""
    You are a surf forecasting expert with deep knowledge of surf breaks worldwide.
    Given the name and region of a surf break, return accurate, real-world details about it.
    Only output data you are reasonably confident about; make sensible best estimates where exact
    figures aren't publicly documented, and never fabricate wildly implausible values.
    Respond ONLY with JSON matching the given schema.
    """)

SEARCH_SYSTEM_PROMPT = textwrap.dedent("""
    You are a surf forecasting expert with deep knowledge of surf breaks worldwide.
    Given the name and region of a surf break, use the web_search tool to check or
    fill in details you're unsure of (swell size/direction, wind, tide, hazards,
    season, access, etc). Call web_search as many times as useful, then reply with
    a concise plain-text summary of everything you found (not JSON yet).
    """)

# One-shot example so the model sees the expected JSON shape and level of detail.
ONE_SHOT_EXAMPLE = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": "Bells Beach, Victoria, Australia"},
    {
        "role": "assistant",
        "content": json.dumps({
            "name": "Bells Beach",
            "region": "VIC",
            "short_description": (
                "Iconic right-hand point/reef break near Torquay, Victoria, "
                "famous as the home of the world's longest-running professional "
                "surf contest, the Rip Curl Pro."
            ),
            "coordinates": {"lat": -38.3697, "lng": 144.2814},
            "ideal_swell": {"size_ft_min": 4, "size_ft_max": 10, "direction": "SW"},
            "ideal_wind": {"strength_kt_max": 12, "direction": "N/NW"},
            "ideal_tide": "mid, either direction",
            "additional_details": {
                "break_type": "point/reef",
                "break_direction": "right",
                "break_surface": "reef",
                "bottom_type": "reef/rock ledge",
                "skill_level": "intermediate to expert",
                "best_season": "March to August (autumn/winter SW swells)",
                "hazards": "rocks, powerful current",
                "other_notes": (
                    "Hosts the Easter Rip Curl Pro, one of the longest-running "
                    "events on the world tour, so it gets very crowded around "
                    "that period; public access via car park and cliff path."
                ),
            },
        }),
    },
]


def search_web(query: str) -> str:
    try:
        results = DDGS().text(query, max_results=3)
        return "\n".join(f"- {r.get('title')}: {r.get('body')}" for r in results)
    except Exception as e:
        return f"[web_search error: {e}]"


def gather_search_context(client: InferenceClient, query: str) -> str:
    """Let the model drive web searches and return its notes.

    The first search is forced so the model can't shortcut straight to an
    answer; after that it decides for itself whether more searches help.
    """
    messages = [
        {"role": "system", "content": SEARCH_SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    notes: list[str] = []

    for round_num in range(MAX_SEARCH_ROUNDS):
        completion = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=[WEB_SEARCH_TOOL],
            tool_choice=(
                {"type": "function", "function": {"name": "web_search"}}
                if round_num == 0
                else "auto"
            ),
            temperature=TEMPERATURE,
            max_tokens=800,
        )
        msg = completion.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)

        if not tool_calls:
            if notes:
                return msg.content or "\n\n".join(notes)
            messages.append({
                "role": "user",
                "content": "You must call web_search at least once before answering.",
            })
            continue

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": tool_calls,
        })
        for call in tool_calls:
            args = json.loads(call.function.arguments or "{}")
            result = search_web(args.get("query", query))
            notes.append(result)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    return "\n\n".join(notes)


def generate_break_details(client: InferenceClient, spot_name: str, region_hint: str) -> dict:
    """Generate structured details for one break via a two-phase call."""
    query = f"{spot_name}, {region_hint}"

    search_context = gather_search_context(client, query)

    completion = client.chat.completions.create(
        model=MODEL,
        messages=ONE_SHOT_EXAMPLE + [{
            "role": "user",
            "content": (
                "Here are some web search notes to help ground your answer "
                "(use them where relevant, ignore anything irrelevant or "
                f"unreliable):\n\n{search_context}\n\n"
                f"Now respond with the final JSON for: {query}"
            ),
        }],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "surf_break", "schema": SURF_BREAK_SCHEMA, "strict": True},
        },
        temperature=TEMPERATURE,
        max_tokens=2000,
    )

    raw = completion.choices[0].message.content
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(f"model returned non-JSON content for '{query}': {raw!r}")

    # Anchor identity fields to the input so lookups match breaks.json even
    # when the model renames the spot (e.g. 'Cronulla - Voodoo' -> 'Voodoo').
    result["name"] = spot_name
    result["region"] = region_hint
    return result


def run_batch() -> None:
    """Fetch details for every break, resumable across runs."""
    with open(INPUT_PATH) as f:
        breaks = json.load(f)

    # Skip entries already fetched successfully; retry failed/missing ones.
    results: dict[tuple[str, str], dict] = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH) as f:
            for entry in json.load(f):
                results[(entry["name"], entry.get("region", ""))] = entry

    client = InferenceClient()  # uses the token stored by `hf auth login`

    for i, entry in enumerate(breaks, start=1):
        name, region = entry["name"], entry["region"]
        key = (name, region)
        if key in results and "error" not in results[key]:
            print(f"[{i}/{len(breaks)}] {name} ({region}) already done, skipping")
            continue

        print(f"[{i}/{len(breaks)}] {name} ({region})...", end=" ", flush=True)
        error = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                results[key] = generate_break_details(client, name, region)
                error = None
                print("ok")
                break
            except Exception as e:
                error = str(e)
                print(f"attempt {attempt}/{MAX_ATTEMPTS} failed: {str(e)[:120]}")
                time.sleep(2 * attempt)

        if error is not None:
            results[key] = {"name": name, "region": region, "error": error}

        # Save after every entry so a crash never loses completed work.
        with open(OUTPUT_PATH, "w") as f:
            json.dump(list(results.values()), f, indent=2)

        time.sleep(1)

    ok = sum(1 for v in results.values() if "error" not in v)
    print(f"\nDone. {ok}/{len(breaks)} breaks fetched successfully, saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    run_batch()
