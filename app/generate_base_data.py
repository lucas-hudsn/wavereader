"""
batch_generate_surf_breaks.py

Iterates through the nested Australia surf-break list (australia_surf_breaks.json)
and calls generate_surf_break() -- imported from generate_surf_break.py -- for
every break, writing schema-valid enriched JSON out incrementally.

Output format (data/australia-surf-breaks-enriched.json) is a JSON *list* of
surf-break objects, each carrying canonical top-level ``state`` and ``region``
filter keys plus a normalized ``location``::

    [
      {
        "name": "Bells Beach",
        "state": "Victoria",
        "region": "Surf Coast",
        "location": {
          "region": "Surf Coast",
          "state": "Victoria",
          "country": "Australia",
          "coordinates": {"lat": -38.3667, "lng": 144.2833}
        },
        ...
      },
      ...
    ]

Filtering is then trivial::

    breaks = load_enriched()
    vic = filter_breaks(breaks, state="Victoria")
    surf_coast = filter_breaks(breaks, state="Victoria", region="Surf Coast")

Directory layout this script assumes (adjust the imports/paths if yours differs):

    project/
      batch_generate_surf_breaks.py      <- this file
      generate_surf_break.py             <- the module with generate_surf_break()
      australia_surf_breaks.json         <- the flat/nested break list to iterate
      data/
        surf-break-schema.json
        surf-break-example-bells.json

Usage:
    export HF_TOKEN=your_hf_token
    uv run python batch_generate_surf_breaks.py

Resumable: if interrupted or if individual calls fail, re-running the script
skips breaks that already have a successful entry in the output file.
Failures are NOT persisted to the output list -- a missing entry is simply
retried on the next run.
"""
import json
import time
from pathlib import Path

from app.generate_surf_break import generate_surf_break

DATA_DIR = Path(__file__).parent.parent / "data"

INPUT_LIST = DATA_DIR / "australia-surf-breaks.json"
OUTPUT_FILE = DATA_DIR / "australia-surf-breaks-enriched.json"

# Pause between API calls (seconds) to avoid hammering the inference provider.
REQUEST_DELAY = 1.0

# How many times to retry a single break before giving up and recording an error.
MAX_RETRIES = 2


def make_key(break_name: str, state: str, region: str) -> str:
    """Canonical resume key for one input break."""
    return f"{break_name} | {state} | {region}"


def load_break_list(path: Path = INPUT_LIST) -> list[dict]:
    """Flatten the nested state -> region -> [break names] structure into a flat list
    of {break_name, state, region} dicts, in a stable order."""
    data = json.loads(path.read_text())
    breaks = []
    for state, regions in data["Australia_Surf_Breaks"].items():
        for region, names in regions.items():
            for name in names:
                breaks.append({"break_name": name, "state": state, "region": region})
    return breaks


def enrich_result(break_info: dict, generated: dict) -> dict:
    """Merge one raw LLM result with its canonical state/region filter keys.

    The canonical ``state``/``region`` come from the input list (not the model)
    so they are always spelled consistently and safe to filter on. The model's
    free-text ``location.region`` (e.g. "North Coast, New South Wales",
    "Northern Beaches, Sydney") is normalized to the same canonical values,
    while ``country``/``coordinates`` from the model are preserved.

    The ``id`` field pins the entry to its canonical input triple, so resume
    keys stay exact even when the model shortens a break name (e.g. two
    distinct inputs that both generate as "Gnaraloo").
    """
    key = make_key(break_info["break_name"], break_info["state"], break_info["region"])
    enriched = {
        "id": key,
        "state": break_info["state"],
        "region": break_info["region"],
        **generated,
    }
    enriched["state"] = break_info["state"]
    enriched["region"] = break_info["region"]
    location = dict(enriched.get("location") or {})
    location["state"] = break_info["state"]
    location["region"] = break_info["region"]
    enriched["location"] = location
    return enriched


def _from_legacy_dict(data: dict) -> dict:
    """Convert the legacy '{"name | state | region}": {...}}' mapping into the
    internal {key: enriched-break} dict, dropping error stubs and normalizing
    surviving entries with their canonical state/region from the key."""
    results = {}
    for key, value in data.items():
        if not isinstance(value, dict) or "error" in value:
            continue
        try:
            break_name, state, region = [p.strip() for p in key.split("|")]
        except ValueError:
            continue
        results[make_key(break_name, state, region)] = enrich_result(
            {"break_name": break_name, "state": state, "region": region}, value
        )
    return results


def load_existing_results(path: Path = OUTPUT_FILE) -> dict:
    """Load whatever has already been generated so a re-run can resume, not restart.

    Returns a {canonical-key: enriched-break} dict regardless of whether the
    file on disk holds the current list format or the legacy keyed-dict format.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        print(f"Warning: {path} was unreadable/corrupt, starting fresh.")
        return {}
    if isinstance(data, list):
        results = {}
        for entry in data:
            if not isinstance(entry, dict) or "error" in entry:
                continue
            # Prefer the stored canonical id; fall back to the generated
            # name triple for entries written before ids were introduced.
            # (Suffixed on collision, since the model occasionally shortens
            # names and two inputs can share one generated name.)
            key = entry.get("id") or make_key(
                entry.get("name", ""),
                entry.get("state", ""),
                entry.get("region", ""),
            )
            if key in results:
                suffix = 2
                while f"{key} #{suffix}" in results:
                    suffix += 1
                key = f"{key} #{suffix}"
            results[key] = entry
        return results
    if isinstance(data, dict):
        return _from_legacy_dict(data)
    print(f"Warning: {path} has an unexpected shape, starting fresh.")
    return {}


def save_results(results: dict, path: Path = OUTPUT_FILE) -> None:
    """Persist results as a list sorted by (state, region, name) for stable diffs
    and easy state/region filtering downstream."""
    ordered = sorted(
        results.values(),
        key=lambda b: (b.get("state", ""), b.get("region", ""), b.get("name", "")),
    )
    path.write_text(json.dumps(ordered, indent=2))


def load_enriched(path: Path = OUTPUT_FILE) -> list[dict]:
    """Load the enriched output as a plain list of break dicts."""
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return [b for b in data if isinstance(b, dict) and "error" not in b]
    # Legacy file: normalize on read.
    return list(_from_legacy_dict(data).values())


def filter_breaks(
    breaks: list[dict], state: str | None = None, region: str | None = None
) -> list[dict]:
    """Filter enriched breaks by canonical state and/or region.

    Matching is exact on the canonical keys, with a case-insensitive fallback::

        filter_breaks(breaks, state="Victoria")
        filter_breaks(breaks, state="Victoria", region="Surf Coast")
    """
    out = breaks
    if state is not None:
        out = [
            b
            for b in out
            if b.get("state") == state
            or str(b.get("state", "")).lower() == state.lower()
        ]
    if region is not None:
        out = [
            b
            for b in out
            if b.get("region") == region
            or str(b.get("region", "")).lower() == region.lower()
        ]
    return out


def generate_with_retries(b: dict, max_retries: int = MAX_RETRIES) -> dict:
    """Call generate_surf_break() with a couple of retries on transient failures."""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            generated = generate_surf_break(
                break_name=b["break_name"],
                state=b["state"],
                region=b["region"],
            )
            return enrich_result(b, generated)
        except Exception as e:  # noqa: BLE001 - we want to catch and record any failure
            last_error = e
            print(f"  ! Attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                time.sleep(2 * attempt)  # simple backoff
    return {"error": str(last_error)}


def main() -> None:
    breaks = load_break_list()
    results = load_existing_results()

    already_done = len(results)
    print(f"Loaded {len(breaks)} surf breaks. {already_done} already generated successfully.")

    failures: list[str] = []
    for i, b in enumerate(breaks, 1):
        key = make_key(b["break_name"], b["state"], b["region"])

        if key in results:
            continue  # already have a good result, skip

        print(f"[{i}/{len(breaks)}] Generating: {key}")
        outcome = generate_with_retries(b)

        if "error" in outcome:
            failures.append(key)
            continue  # don't persist error stubs; a re-run retries missing entries

        results[key] = outcome

        # Save after every break so a crash or rate-limit doesn't lose progress.
        save_results(results)

        time.sleep(REQUEST_DELAY)

    succeeded = len(results)
    print(f"Done. {succeeded} succeeded, {len(failures)} failed. Wrote results to {OUTPUT_FILE}")
    for key in failures:
        print(f"  - failed (will retry next run): {key}")


if __name__ == "__main__":
    main()
