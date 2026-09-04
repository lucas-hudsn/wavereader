# WaveReader API Reference

FastAPI backend exposing deterministic surf forecast and scoring endpoints along with agent question-answering.

Base URL: `http://localhost:8000` (or the deployed host)  
Interactive OpenAPI documentation: `http://localhost:8000/docs`

---

## Endpoints

### 1. Health Check

```http
GET /
```

Returns system health and service version.

**Response:**
```json
{
  "name": "wavereader",
  "version": "0.1.0",
  "status": "ok"
}
```

---

### 2. List / Search Spots

```http
GET /spots?query={query}&region={region}&skill={skill}&limit={limit}
```

Search 100 Australian surf breaks by query string, state code, or skill suitability.

**Query Parameters:**
| Parameter | Type | Required | Description |
|---|---|:---:|---|
| `query` | string | No | Search query over break names or regions (e.g., `"Snapper"`, `"QLD"`). |
| `region` | string | No | Australian state/territory filter (`NSW`, `QLD`, `VIC`, `WA`, `SA`, `TAS`). |
| `skill` | string | No | Filter by skill suitability (`beginner`, `intermediate`, `advanced`, `expert`). |
| `limit` | integer | No | Maximum number of results to return (default: `10`). |

**Example:**
```bash
curl "http://localhost:8000/spots?region=QLD&skill=beginner&limit=3"
```

**Response (200 OK):**
```json
[
  {
    "name": "Rainbow Bay",
    "region": "QLD",
    "coordinates": {"lat": -28.163, "lng": 153.543},
    "ideal_swell": {"size_ft_min": 2.0, "size_ft_max": 5.0, "direction": "E/SE"},
    "ideal_wind": {"direction": "SE, S", "strength_kt_max": 18.0},
    "ideal_tide": "Low to mid rising",
    "additional_details": {
      "skill_level": "Beginner to intermediate",
      "hazards": "Crowds, sandy bottom",
      "crowd_level": "High"
    }
  }
]
```

---

### 3. Get Spot Profile

```http
GET /spots/{spot_name}?region={region}
```

Returns the full knowledge-base profile for a single break.

**Path Parameters:**
| Parameter | Type | Description |
|---|---|---|
| `spot_name` | string | Exact name of the break (e.g., `Snapper Rocks`). |

**Query Parameters:**
| Parameter | Type | Required | Description |
|---|---|:---:|---|
| `region` | string | Yes | State/territory of the break (`NSW`, `QLD`, etc.). |

**Example:**
```bash
curl "http://localhost:8000/spots/Bells%20Beach?region=VIC"
```

**Response (200 OK):**
```json
{
  "name": "Bells Beach",
  "region": "VIC",
  "coordinates": {"lat": -38.371, "lng": 144.282},
  "ideal_swell": {"size_ft_min": 4.0, "size_ft_max": 12.0, "direction": "SW, S"},
  "ideal_wind": {"direction": "NW, WNW", "strength_kt_max": 20.0},
  "ideal_tide": "Mid to high",
  "additional_details": {
    "skill_level": "Advanced to expert",
    "hazards": "Reef bottom, heavy hold-downs, cold water",
    "crowd_level": "High"
  }
}
```

**Errors:**
- `404 Not Found`: If the spot is not found in the named region.

---

### 4. Hourly Forecast

```http
GET /forecast?spot={spot}&region={region}&days={days}
```

Fetches hourly marine and weather forecasts from Open-Meteo, snapped seaward of the coast and cached locally.

**Query Parameters:**
| Parameter | Type | Required | Description |
|---|---|:---:|---|
| `spot` | string | Yes | Spot name. |
| `region` | string | Yes | Australian region/state code. |
| `days` | integer | No | Forecast horizon in days (default: `7`). |

**Example:**
```bash
curl "http://localhost:8000/forecast?spot=Snapper%20Rocks&region=QLD&days=2"
```

**Response (200 OK):**
```json
{
  "latitude": -28.15,
  "longitude": 153.68,
  "hourly": [
    {
      "time": "2026-09-04T00:00",
      "wave_height": 1.4,
      "wave_period": 11.2,
      "wave_direction": 125.0,
      "wind_speed_10m": 14.5,
      "wind_direction_10m": 160.0
    }
  ]
}
```

---

### 5. Deterministic Surf Quality Score

```http
GET /score?spot={spot}&region={region}&days={days}&skill={skill}
```

Calculates deterministic hour-by-hour surf quality scores (0.0 to 10.0) calibrated against the break's ideal bathymetry and the surfer's skill level.

**Query Parameters:**
| Parameter | Type | Required | Description |
|---|---|:---:|---|
| `spot` | string | Yes | Spot name. |
| `region` | string | Yes | State/region code. |
| `days` | integer | No | Forecast horizon in days (default: `7`). |
| `skill` | string | No | Surfer skill level: `beginner`, `intermediate`, `advanced`, `expert` (default: `intermediate`). |

**Example:**
```bash
curl "http://localhost:8000/score?spot=Snapper%20Rocks&region=QLD&skill=beginner"
```

**Response (200 OK):**
```json
[
  {
    "time": "2026-09-04T06:00",
    "score": 7.42,
    "skill_level": "beginner",
    "components": {
      "swell_size": 8.5,
      "swell_direction": 7.8,
      "wind": 6.9,
      "period": 8.0
    },
    "wave_height_m": 1.1,
    "wave_period_s": 10.5,
    "wind_speed_kt": 9.2,
    "wind_direction_deg": 180.0,
    "wave_direction_deg": 130.0
  }
]
```

---

### 6. Ask Agent

```http
POST /ask
Content-Type: application/json
```

Asks a natural-language question to the `smolagents` CodeAgent. The agent invokes deterministic tools to retrieve and interpret data.

**Request Body:**
```json
{
  "question": "What time should I surf Snapper Rocks tomorrow morning as an intermediate?",
  "provider": "hf",
  "model": null
}
```

| Field | Type | Required | Description |
|---|---|:---:|---|
| `question` | string | Yes | Natural language surf forecasting question. |
| `provider` | string | No | LLM host: `"hf"` (Hugging Face) or `"nim"` (NVIDIA NIM). Defaults to auto-detect. |
| `model` | string | No | Optional model ID override. |

**Response (200 OK):**
```json
{
  "answer": "For Snapper Rocks tomorrow morning, optimal conditions are between 6:00 AM and 8:00 AM...",
  "trace": "{\"question\": \"...\", \"events\": [...]}"
}
```

**Errors:**
- `503 Service Unavailable`: If `HF_TOKEN` or `NVIDIA_API_KEY` are unset for the requested provider.
- `502 Bad Gateway`: If the upstream model inference router fails.
