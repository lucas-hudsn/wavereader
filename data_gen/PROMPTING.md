# Prompt Engineering Documentation

## Zero Shot Prompting

Zero-shot prompting involves asking the model to perform a task without providing any examples. The model relies entirely on its pre-trained knowledge and the instructions provided in the prompt.

### Principles Used

**1. Structured Output Format**

We specified the exact JSON structure we wanted returned, listing each field explicitly:

```
Return a JSON object with the following fields:
- "description": A quick 2-3 sentence description of the break
- "state": The state/region where it's located
...
```

This removes ambiguity about what format the response should take.

**2. Constrained Options**

For fields with limited valid values, we explicitly listed the allowed options:

```
- "wave_direction": Either "left" or "right"
- "bottom_type": Either "reef" or "sand"
- "skill_level": Either "beginner", "intermediate", or "advanced"
```

This prevents the model from inventing its own categories and ensures consistent, parseable data.

**3. Clear Output Instructions**

We added explicit formatting constraints at the end of the prompt:

```
Return ONLY valid JSON, no markdown or additional text.
```

This reduces the chance of the model wrapping the response in markdown code blocks or adding explanatory text that would break JSON parsing.

**4. Inline Examples**

For less obvious fields, we provided example formats:

```
- "ideal_swell_size": Ideal swell size range in feet (e.g., "3-6 ft")
```

This guides the model toward the expected format without providing a full few-shot example.

### Results

Using these principles, the model returned well-structured data for Bells Beach:

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

The response followed all specified constraints and returned valid, parseable JSON.

## One-Shot Prompting

One-shot prompting provides the model with a single example of the desired input-output pair before asking it to perform the task. This helps the model understand not just the format but also the style, tone, and level of detail expected.

### Why One-Shot Over Zero-Shot?

When scaling to many similar requests (e.g., 50 surf breaks), one-shot prompting offers advantages:

1. **Consistency** - The example anchors the model's responses to a known-good output
2. **Implicit style guide** - The example demonstrates the expected level of detail and writing style
3. **Reduced ambiguity** - The model can infer expectations that are hard to specify explicitly

### Implementation

We used the validated Bells Beach result from zero-shot prompting as our example:

```python
BELLS_BEACH_EXAMPLE = {
    "name": "Bells Beach",
    "description": "Bells Beach is a world-renowned right-hand point break...",
    "state": "Victoria",
    "coordinates": {"latitude": -38.366, "longitude": 144.279},
    ...
}
```

The prompt structure follows an Input/Output pattern:

```
Here is an example for Bells Beach:

Input: Bells Beach
Output:
{json example}

Now provide the same information for the following surf break.

Input: {beach_name}
Output:
```

### Key Differences from Zero-Shot

| Aspect | Zero-Shot | One-Shot |
|--------|-----------|----------|
| Examples provided | None | One complete example |
| Token usage | Lower | Higher (includes example) |
| Output consistency | Good with constraints | Better with real example |
| Use case | Single queries | Batch processing |

### Scaling Considerations

When processing 50 surf breaks:

1. **Database storage** - Results are saved to PostgreSQL with upsert logic to handle reruns
2. **Error handling** - Individual failures don't stop the batch
3. **Progress tracking** - Console output shows progress through the list

### Script

See `generate_australia_surfbreaks_oneshot.py` for the full implementation.
