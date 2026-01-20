# Prompt Engineering for Surf Break Data Generation

This document covers the prompting techniques used to populate the wave~reader database with 50+ Australian surf breaks.

## Overview

Two prompting strategies were developed:

1. **Zero-shot** - Explicit instructions without examples
2. **One-shot** - Single validated example to anchor output

## Zero-Shot Prompting

Zero-shot prompting asks the model to perform a task using only instructions, relying on its pre-trained knowledge.

### Principles

**1. Structured Output**

Define the exact JSON schema:

```
Return a JSON object with the following fields:
- "description": A quick 2-3 sentence description
- "state": The state/region where it's located
- "coordinates": Object with "latitude" and "longitude"
...
```

**2. Constrained Options**

Limit valid values for categorical fields:

```
- "wave_direction": Either "left" or "right"
- "bottom_type": Either "reef" or "sand"
- "skill_level": Either "beginner", "intermediate", or "advanced"
```

**3. Format Examples**

Provide inline hints for ambiguous fields:

```
- "ideal_swell_size": Ideal swell size range (e.g., "3-6 ft")
```

**4. Clear Output Instructions**

Prevent markdown wrapping or explanatory text:

```
Return ONLY valid JSON, no markdown or additional text.
```

### Example Output

```json
{
  "description": "Bells Beach is a world-renowned right-hand point break...",
  "state": "Victoria",
  "coordinates": { "latitude": -38.366, "longitude": 144.279 },
  "wave_direction": "right",
  "bottom_type": "reef",
  "break_type": "point",
  "skill_level": "advanced",
  "ideal_wind": "Light offshore (NW to N)",
  "ideal_tide": "Mid to high",
  "ideal_swell_size": "4-10 ft"
}
```

## One-Shot Prompting

One-shot prompting provides a single example input-output pair before the actual request.

### Why One-Shot?

When generating data for 50 surf breaks, one-shot offers advantages:

| Benefit | Description |
|---------|-------------|
| Consistency | Output anchored to known-good example |
| Style matching | Tone and detail level preserved |
| Reduced ambiguity | Model infers unstated expectations |

### Implementation

Use a validated result as the example:

```python
BELLS_BEACH_EXAMPLE = {
    "name": "Bells Beach",
    "description": "Bells Beach is a world-renowned right-hand point break...",
    "state": "Victoria",
    "coordinates": {"latitude": -38.366, "longitude": 144.279},
    "wave_direction": "right",
    "bottom_type": "reef",
    "break_type": "point",
    "skill_level": "advanced",
    "ideal_wind": "Light offshore (NW to N)",
    "ideal_tide": "Mid to high",
    "ideal_swell_size": "4-10 ft",
}

prompt = f"""Provide detailed information about a surf break.

Here is an example for Bells Beach:

Input: Bells Beach
Output:
{json.dumps(BELLS_BEACH_EXAMPLE, indent=2)}

Now provide the same information for:

Input: {beach_name}
Output:"""
```

### Input/Output Pattern

The prompt follows a clear structure:

1. Task description
2. Example (Input → Output)
3. Actual request (Input → ...)

This pattern helps the model understand exactly what format to produce.

## Comparison

| Aspect | Zero-Shot | One-Shot |
|--------|-----------|----------|
| Token usage | Lower | Higher (includes example) |
| Consistency | Good with constraints | Excellent |
| Style matching | Variable | Anchored to example |
| Best for | Single queries | Batch processing |

## Batch Processing

The one-shot script processes all 50 breaks with:

- **Database storage** - PostgreSQL upsert for reruns
- **Error handling** - Individual failures don't stop batch
- **Progress tracking** - Console output shows progress

```python
AUSTRALIAN_SURF_BREAKS = [
    "Snapper Rocks", "Kirra", "Burleigh Heads", "Noosa",
    "North Narrabeen", "Bondi Beach", "Bells Beach", "Margaret River",
    # ... 50 total
]

for i, beach in enumerate(AUSTRALIAN_SURF_BREAKS, 1):
    print(f"[{i}/50] Fetching {beach}...")
    try:
        details = get_beach_details(beach)
        save_to_database(cursor, conn, details)
    except Exception as e:
        print(f"  Error: {e}")
```

## Scripts

| Script | Approach | Purpose |
|--------|----------|---------|
| `generate_bellsbeach_data_zeroshot.py` | Zero-shot | Single break example |
| `generate_australia_surfbreaks_oneshot.py` | One-shot | Batch generation (50 breaks) |
