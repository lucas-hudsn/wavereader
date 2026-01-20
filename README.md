# wave~reader

AI-powered surf forecasting for 50+ Australian surf breaks using Google Gemini and real-time marine weather data.

## Overview

wave~reader is a full-stack web application that helps surfers find optimal conditions at Australian surf breaks. It combines:

- A curated SQLite database of 51 Australian surf breaks with detailed characteristics
- Real-time marine and weather data from Open-Meteo APIs
- AI-generated weekly surf forecasts using Google Gemini

Users browse surf breaks by state, view detailed break information, see weekly conditions charts, and read AI-powered surf reports.

## Quick Start

```bash
# Install dependencies
uv sync

# Set up environment variables
cp .env.example .env
# Edit .env with your GEMINI_API_KEY

# Populate database (if needed)
uv run python data_gen/generate_australia_surfbreaks_oneshot.py

# Run development server
uv run uvicorn main:app --reload
```

Visit `http://localhost:8000`

## Requirements

- Python 3.14+
- Google Gemini API key
- uv package manager

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key | Required |
| `POSTGRES_HOST` | PostgreSQL host | localhost |
| `POSTGRES_PORT` | PostgreSQL port | 5432 |
| `POSTGRES_DB` | Database name | wavereader |
| `POSTGRES_USER` | Database user | postgres |
| `POSTGRES_PASSWORD` | Database password | "" |

**Note:** The application currently uses SQLite (`data/wavereader.db`) for simplicity. The data generation script can use PostgreSQL if configured.

---

# Part 1: Data Generation

## Overview

The data generation system populates the surf break database using Google Gemini AI to generate detailed information about each break. The process uses one-shot prompting with Bells Beach as the example.

## Files

| File | Purpose |
|------|---------|
| `data_gen/generate_australia_surfbreaks_oneshot.py` | Main data generation script (235 lines) |
| `data_gen/generate_bellsbeach_data_zeroshot.py` | Zero-shot example script |
| `data_gen/PROMPTING.md` | Prompt engineering guide |

## surf_breaks_list

The script generates data for 51 Australian surf breaks across all coastal states:

**Queensland (14 breaks)**
- Snapper Rocks, Kirra, Burleigh Heads, Duranbah, Greenmount, The Superbank
- Noosa, Moffat Beach, Alexandra Headland, Coolum Beach, Sunshine Beach
- Rainbow Bay, Fingal Head, Cabarita Beach, Kingscliff, Palm Beach (QLD), Currumbin, Coolangatta

**New South Wales (11 breaks)**
- North Narrabeen, Manly Beach, Bondi Beach, Maroubra, Cronulla
- Angourie, Lennox Head, Byron Bay - The Pass, Crescent Head
- Southport, Straddie (North Stradbroke Island)

**Victoria (11 breaks)**
- Torquay, Jan Juc, Winkipop, Johanna Beach, Portsea, Gunnamatta
- Phillip Island, Woolamai, Bells Beach

**Western Australia (8 breaks)**
- Margaret River, The Box (Margaret River), Yallingup
- Trigg Beach, Scarborough Beach, Rottnest Island

**South Australia (8 breaks)**
- Cactus Beach, Pennington Bay, Vivonne Bay, Parsons Beach
- Waitpinga Beach, Middleton, Goolwa Beach

## Data Structure

Each surf break is stored with the following fields:

```python
{
    "name": str,                    # Unique break name
    "description": str,             # 2-3 sentence description
    "state": str,                   # Australian state
    "coordinates": {
        "latitude": float,          # Decimal degrees
        "longitude": float
    },
    "wave_direction": str,          # "left" or "right"
    "bottom_type": str,             # "reef" or "sand"
    "break_type": str,              # "point" or "beach"
    "skill_level": str,             # "beginner", "intermediate", "advanced"
    "ideal_wind": str,              # e.g., "Light offshore (NW to N)"
    "ideal_tide": str,              # e.g., "Mid to high"
    "ideal_swell_size": str,        # e.g., "3-6 ft"
}
```

## One-Shot Prompting Strategy

The data generation uses one-shot prompting to ensure consistent output format:

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
```

The prompt provides this example and asks Gemini to generate the same structure for each break.

## Running Data Generation

```bash
uv run python data_gen/generate_australia_surfbreaks_oneshot.py
```

Output:
```
Initializing database...
Saving Bells Beach example...
[1/51] Fetching details for Snapper Rocks...
  Saved: Snapper Rocks
[2/51] Fetching details for Kirra...
  Saved: Kirra
...
Done! All surf breaks saved to database.
```

## Database Schema

The data generation script creates a PostgreSQL-compatible schema:

```sql
CREATE TABLE surf_breaks (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    state VARCHAR(100),
    latitude DECIMAL(10, 6),
    longitude DECIMAL(10, 6),
    wave_direction VARCHAR(20),
    bottom_type VARCHAR(20),
    break_type VARCHAR(20),
    skill_level VARCHAR(20),
    ideal_wind VARCHAR(255),
    ideal_tide VARCHAR(255),
    ideal_swell_size VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

The production application uses SQLite with the same schema structure.

---

# Part 2: Backend

## Overview

The backend is a FastAPI application that serves HTML pages, REST APIs, and integrates with external services (Open-Meteo and Google Gemini).

## File Structure

```
wavereader/
├── main.py                      # FastAPI application (233 lines)
├── data/
│   ├── wavereader.db           # SQLite database (36KB)
│   └── surf_breaks.csv         # Data export
├── templates/                   # Jinja2 HTML templates
│   ├── landing.html            # Home page (55 lines)
│   └── break.html              # Break details page (119 lines)
└── static/                      # Static assets
    ├── style.css               # Retro monospace theme (521 lines)
    ├── landing.js              # Landing page logic (85 lines)
    └── break.js                # Break details + charts (267 lines)
```

## Core Configuration

```python
# Paths
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "wavereader.db"

# FastAPI app setup
app = FastAPI()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Gemini client
GEMINI_CLIENT = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
REPORT_MODEL = "gemma-3-27b-it"
```

## Database Connection

```python
def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    return conn

def serialize_row(row: sqlite3.Row) -> dict:
    return dict(row)
```

## External API Integration

### Open-Meteo API

The backend fetches marine and weather data from two Open-Meteo endpoints:

**Marine API** (`https://marine-api.open-meteo.com/v1/marine`)
```python
marine_params = {
    "latitude": latitude,
    "longitude": longitude,
    "hourly": ["wave_height", "wave_period", "wave_direction"],
    "daily": ["wave_height_max", "wave_period_max"],
    "timezone": "auto",
    "forecast_days": 7,
}
```

**Weather API** (`https://api.open-meteo.com/v1/forecast`)
```python
weather_params = {
    "latitude": latitude,
    "longitude": longitude,
    "hourly": ["wind_speed_10m", "wind_direction_10m"],
    "daily": ["wind_speed_10m_max", "wind_direction_10m_dominant"],
    "timezone": "auto",
    "forecast_days": 7,
}
```

### Google Gemini API

The forecast generation prompt:

```python
prompt = f"""Generate a daily surf report for {break_info.get('name')}:

SURF BREAK INFORMATION:
- Name: {break_info.get('name')}
- Description: {break_info.get('description')}
- Break Type: {break_info.get('break_type')}
- Bottom Type: {break_info.get('bottom_type')}
- Wave Direction: {break_info.get('wave_direction')}
- Skill Level: {break_info.get('skill_level')}
- Ideal Wind: {break_info.get('ideal_wind')}
- Ideal Tide: {break_info.get('ideal_tide')}
- Ideal Swell Size: {break_info.get('ideal_swell_size')}

7-DAY FORECAST SUMMARY:
{daily_conditions}

Create a daily surf report with:
1. Week Overview (2-3 sentences)
2. Best Days (specific days and why)
3. Swell Trend
4. Wind Pattern
5. Recommended Sessions
6. Who Should Surf

Be specific and practical."""
```

## API Endpoints

### REST API Endpoints

| Endpoint | Method | Description | Response |
|----------|--------|-------------|----------|
| `/api/states` | GET | List all states with surf breaks | `{"states": ["Victoria", "Queensland", ...]}` |
| `/api/breaks` | GET | List all breaks (id, name, state, coords, skill) | `{"breaks": [{id, name, state, ...}, ...]}` |
| `/api/breaks/{state}` | GET | List break names for a state | `{"breaks": ["Bells Beach", "Jan Juc", ...]}` |
| `/api/break/{name}` | GET | Get full break details + weather + AI forecast | JSON with all data |
| `/health` | GET | Health check | `{"status": "ok"}` |

### HTML Page Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Landing page with state/break dropdowns |
| `/{state}/{break_name}` | GET | Surf break details page |

### Endpoint Implementation Examples

**List all states:**
```python
@app.get("/api/states")
async def get_states():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT state FROM surf_breaks ORDER BY state")
        states = [row["state"] for row in cursor.fetchall()]
        conn.close()
        return JSONResponse({"states": states})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
```

**Get break details with weather and forecast:**
```python
@app.get("/api/break/{name}")
async def get_break_details(name: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""SELECT * FROM surf_breaks WHERE name = ?""", (name,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return JSONResponse({"error": "Surf break not found"}, status_code=404)

        break_info = serialize_row(row)

        # Fetch weather data
        latitude = break_info.get("latitude")
        longitude = break_info.get("longitude")
        if latitude and longitude:
            weather_data = query_openmeteo(latitude, longitude)
            if weather_data.get("success"):
                forecast = generate_forecast(break_info, weather_data)
                break_info["weather_data"] = weather_data
                break_info["forecast"] = forecast

        return JSONResponse(break_info)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
```

## Response Formats

### /api/states Response
```json
{
  "states": ["Victoria", "Queensland", "New South Wales", "Western Australia", "South Australia"]
}
```

### /api/break/{name} Response
```json
{
  "name": "Bells Beach",
  "description": "Bells Beach is a world-renowned right-hand point break...",
  "state": "Victoria",
  "latitude": -38.366,
  "longitude": 144.279,
  "wave_direction": "right",
  "bottom_type": "reef",
  "break_type": "point",
  "skill_level": "advanced",
  "ideal_wind": "Light offshore (NW to N)",
  "ideal_tide": "Mid to high",
  "ideal_swell_size": "4-10 ft",
  "weather_data": {
    "success": true,
    "wave_height_max": 2.5,
    "wave_period_max": 12,
    "wind_speed_max": 25,
    "wind_direction": 320,
    "hourly": {
      "time": ["2026-01-20T00:00:00", ...],
      "wave_height": [1.2, 1.4, ...],
      "wave_period": [10, 11, ...],
      "wave_direction": [280, 285, ...],
      "wind_speed": [15, 12, ...],
      "wind_direction": [320, 315, ...]
    },
    "timezone": "Australia/Sydney"
  },
  "forecast": "## Week Overview\n\nThe upcoming week at Bells Beach..."
}
```

## Data Flow

```
User Request
     |
     v
+--------------------+
| FastAPI Route      |  - Receives request
+--------------------+
     |
     v
+--------------------+
| Database Query     |  - SQLite surf_breaks table
+--------------------+
     |
     v
+--------------------+
| Open-Meteo APIs    |  - Marine: wave_height, period, direction
|                    |  - Weather: wind_speed, direction
+--------------------+
     |
     v
+--------------------+
| Gemini API         |  - Generates surf forecast
+--------------------+
     |
     v
+--------------------+
| JSON Response      |  - Returns combined data
+--------------------+
```

---

# Part 3: Frontend

## Overview

The frontend is a server-side rendered application using Jinja2 templates with vanilla JavaScript for interactivity. It features a retro monospace design theme.

## Templates

### landing.html (55 lines)

The landing page serves as the main entry point:

**Structure:**
```html
<body>
    <div class="container">
        <header>
            <h1><a href="/">wave~reader</a></h1>
            <p class="tagline">Australian Surf Forecasting</p>
        </header>

        <main>
            <section class="hero">
                <p>Select a surf break to view detailed forecasts...</p>
            </section>

            <section class="dropdown-section">
                <div class="dropdown-group">
                    <label for="stateSelect">Select State</label>
                    <select id="stateSelect">
                        <option value="">-- Choose a state --</option>
                    </select>
                </div>

                <div class="dropdown-group">
                    <label for="breakSelect">Select Surf Break</label>
                    <select id="breakSelect" disabled>
                        <option value="">-- Choose a surf break --</option>
                    </select>
                </div>
            </section>

            <div id="loadingSpinner" class="loading">...</div>
            <div id="errorContainer" class="error hidden"></div>
        </main>

        <footer>...</footer>
    </div>
    <script src="landing.js"></script>
</body>
```

**Components:**
- State dropdown (populated via API)
- Break dropdown (disabled until state selected)
- Loading spinner
- Error container

### break.html (119 lines)

The surf break details page displays comprehensive information:

**Sections:**
1. **Info Card** - Name, description, state, coordinates
2. **Details Grid** - Wave direction, bottom type, break type, skill level
3. **Conditions Card** - Ideal wind, tide, swell size
4. **Chart Card** - SVG wave height chart + wind direction arrows
5. **Forecast Card** - AI-generated surf report

**Structure:**
```html
<section id="breakDetails" class="break-details hidden">
    <div class="card info-card">
        <h2 id="breakName"></h2>
        <div id="breakDescription" class="description-box"></div>
        <div class="details-grid">
            <!-- Break characteristics -->
        </div>
    </div>

    <div class="card conditions-card">
        <h3>Ideal Conditions</h3>
        <div class="conditions-grid">
            <!-- Ideal wind, tide, swell -->
        </div>
    </div>

    <div class="card chart-card">
        <h3>Weekly Conditions</h3>
        <div id="chartContainer" class="lofi-chart hidden">
            <div class="swell-line-chart" id="swellChart"></div>
            <div class="wind-chart-container" id="windChart"></div>
            <div class="chart-times" id="chartTimes"></div>
        </div>
    </div>

    <div class="card forecast-card">
        <h3>Daily Surf Report</h3>
        <div id="forecastContent" class="forecast-text hidden"></div>
    </div>
</section>
```

## JavaScript

### landing.js (85 lines)

Handles state and break selection:

**Functions:**
- `loadStates()` - Fetches states from `/api/states`
- `handleStateChange()` - Fetches breaks for selected state
- `handleBreakChange()` - Navigates to break page
- `showError()` - Displays error messages

**Flow:**
```
DOMContentLoaded
     |
     v
loadStates() -> /api/states
     |
     v
User selects state
     |
     v
handleStateChange() -> /api/breaks/{state}
     |
     v
breakSelect enabled
     |
     v
User selects break
     |
     v
window.location.href = /{state}/{break_name}
```

### break.js (267 lines)

Fetches and displays break details with charts:

**Functions:**
- `loadBreakDetails()` - Fetches break data from `/api/break/{name}`
- `displayBreakDetails()` - Renders break info to DOM
- `renderChart()` - Orchestrates chart rendering
- `renderSwellLineChart()` - SVG line chart for wave height
- `renderWindArrows()` - Wind direction arrows with tooltips
- `formatForecast()` - Formats AI forecast text
- `getWindDirection()` - Converts degrees to cardinal direction

**Chart Rendering:**

The swell chart uses SVG to render a line graph with area fill:

```javascript
function renderSwellLineChart(container, data, maxHeight) {
    const points = data.map((d, i) => ({
        x: (i / (data.length - 1)) * 100,
        y: padding.top + chartHeight - ((d.waveHeight / maxHeight) * chartHeight),
        value: d.waveHeight,
        time: d.time
    }));

    const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
    const areaPath = `${linePath} L ${points[points.length - 1].x} ${height} L ${points[0].x} ${height} Z`;

    let svg = `<svg viewBox="0 0 100 ${height}" preserveAspectRatio="none">`;
    svg += `<path class="swell-area" d="${areaPath}"/>`;
    svg += `<path class="swell-line" d="${linePath}"/>`;

    points.forEach((p, i) => {
        svg += `<circle class="swell-point" cx="${p.x}" cy="${p.y}" r="2" data-index="${i}"/>`;
    });

    svg += '</svg>';
    container.innerHTML = svg;
}
```

**Wind Arrows:**

Wind direction arrows are sized by speed and rotated by direction:

```javascript
function renderWindArrows(container, data, maxSpeed) {
    data.forEach((d, i) => {
        const speedRatio = d.avgWindSpeed / maxSpeed;
        const arrowSize = 16 + (speedRatio * 24);
        const heightPct = 25 + (speedRatio * 70);
        const arrowRotation = d.windDir;

        windBar.innerHTML = `
            <div class="wind-arrow-container" style="height: ${heightPct}%;">
                <span class="wind-arrow" style="font-size: ${arrowSize}px; transform: rotate(${arrowRotation}deg);">↓</span>
            </div>
        `;
    });
}
```

**Forecast Formatting:**

AI-generated text is formatted for HTML display:

```javascript
function formatForecast(text) {
    return text
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>')
        .replace(/^(\d+\.)/gm, '<br>$1');
}
```

## CSS Styling

### style.css (521 lines)

**Design System:**
- **Theme:** Retro monospace ("Courier New", monospace)
- **Colors:** Ocean palette (#4a90a4 primary, #7bc4d9 accent)
- **Layout:** CSS Grid + Flexbox
- **Responsive:** Mobile breakpoint at 768px

**Color Palette:**
```css
:root {
    --ocean-dark: #1a3a4a;
    --ocean-primary: #4a90a4;
    --ocean-light: #7bc4d9;
    --sand: #e8dcc4;
    --white: #ffffff;
    --error-red: #c94a4a;
    --success-green: #4ac97d;
}
```

**Key Components:**

**Cards:**
```css
.card {
    background: var(--white);
    border: 2px solid var(--ocean-primary);
    border-radius: 4px;
    padding: 20px;
    margin-bottom: 20px;
    box-shadow: 4px 4px 0 var(--ocean-dark);
}
```

**Loading Spinner:**
```css
.spinner {
    width: 40px;
    height: 40px;
    border: 4px solid var(--ocean-light);
    border-top-color: var(--ocean-primary);
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}
```

**Swell Chart:**
```css
.swell-line-chart {
    height: 100px;
    position: relative;
}

.swell-area {
    fill: var(--ocean-light);
    opacity: 0.3;
}

.swell-line {
    fill: none;
    stroke: var(--ocean-primary);
    stroke-width: 2;
}

.swell-point {
    fill: var(--ocean-primary);
    cursor: pointer;
}
```

**Wind Arrows:**
```css
.wind-bar {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-end;
}

.wind-arrow {
    color: var(--ocean-primary);
    display: block;
    transition: transform 0.2s;
}

.wind-arrow:hover {
    color: var(--ocean-dark);
}
```

## Data Flow Diagrams

### Landing Page Flow
```
User visits "/" 
     |
     v
landing.html + landing.js loads
     |
     v
landing.js calls GET /api/states
     |
     v
main.py queries:
     SELECT DISTINCT state FROM surf_breaks ORDER BY state
     |
     v
States returned -> Dropdown populated
     |
     v
User selects "Victoria"
     |
     v
landing.js calls GET /api/breaks/Victoria
     |
     v
main.py queries:
     SELECT name FROM surf_breaks WHERE state = 'Victoria' ORDER BY name
     |
     v
Breaks returned -> Break dropdown populated
     |
     v
User selects "Bells Beach"
     |
     v
window.location.href = /Victoria/Bells%20Beach
```

### Break Details Page Flow
```
URL: /Victoria/Bells%20Beach
     |
     v
break.html + break.js loads
     |
     v
break.js calls GET /api/break/Bells%20Beach
     |
     v
main.py queries SQLite:
     SELECT * FROM surf_breaks WHERE name = 'Bells Beach'
     |
     v
Break details returned
     |
     v
query_openmeteo(-38.366, 144.279):
     |
     v
GET https://marine-api.open-meteo.com/v1/marine?...
GET https://api.open-meteo.com/v1/forecast?...
     |
     v
Weather data returned
     |
     v
generate_forecast(break_info, weather_data):
     |
     v
POST to Gemini (gemma-3-27b-it)
     |
     v
AI forecast returned
     |
     v
Complete response returned to frontend
     |
     v
break.js renders:
     - Break details in info card
     - SVG chart from weather_data.hourly
     - AI forecast text in forecast card
```

---

# Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER'S BROWSER                                  │
│  ┌─────────────────┐  ┌─────────────────┐                                   │
│  │  landing.html   │  │   break.html    │                                   │
│  │  + landing.js   │  │   + break.js    │                                   │
│  │  + style.css    │  │   + SVG Charts  │                                   │
│  └────────┬────────┘  └────────┬────────┘                                   │
│           │                    │                                             │
│           └──────────┬────────┘                                             │
│                      │                                                       │
└──────────────────────┼───────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FASTAPI BACKEND (main.py)                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      API ENDPOINTS                                    │   │
│  │  GET /api/states         → List all states                           │   │
│  │  GET /api/breaks/{state} → List breaks in state                      │   │
│  │  GET /api/break/{name}   → Get break details + weather + forecast    │   │
│  │  GET /                   → Landing page (HTML)                       │   │
│  │  GET /{state}/{name}     → Break details page (HTML)                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                   SERVICE FUNCTIONS                                   │   │
│  │  query_openmeteo()     → Fetch marine + weather data                 │   │
│  │  generate_forecast()   → AI forecast generation via Gemini           │   │
│  │  get_db_connection()   → SQLite database connection                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└───────────────────────┬─────────────────────────────────────────────────────┘
                        │
         ┌──────────────┴──────────────┐
         │                             │
         ▼                             ▼
┌─────────────────────┐   ┌───────────────────────────────────────────────────┐
│   SQLite DB         │   │              EXTERNAL APIs                        │
│   wavereader.db     │   │                                                       │
│                     │   │  ┌─────────────────┐  ┌─────────────────┐         │
│  surf_breaks table  │   │  │   Google Gemini │  │   Open-Meteo     │         │
│  (51 rows)          │   │  │   gemma-3-27b-it│  │   Marine/Weather │         │
│                     │   │  │   Forecast Gen  │   │   APIs           │         │
└─────────────────────┘   │  └─────────────────┘  └─────────────────┘         │
                          └───────────────────────────────────────────────────┘
```

---

# Dependencies

## Core Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi[standard]` | >=0.128.0 | Web framework with automatic API docs |
| `uvicorn[standard]` | >=0.31.0 | ASGI server |
| `jinja2` | >=3.1.2 | Template engine for HTML rendering |
| `requests` | >=2.32.0 | HTTP client for Open-Meteo APIs |
| `pydantic` | >=2.0.0 | Data validation |
| `python-dotenv` | >=1.0.0 | Environment variable loading |
| `google-genai` | >=1.0.0 | Google Gemini API client |

## Development Tools

| Tool | Purpose |
|------|---------|
| `uv` | Package manager (Python 3.14+) |
| `pytest` | Testing framework |

## External APIs

| API | Purpose | Authentication |
|-----|---------|----------------|
| **Google Gemini** | AI forecast generation | `GEMINI_API_KEY` |
| **Open-Meteo Marine** | Wave height, period, direction | None |
| **Open-Meteo Weather** | Wind speed and direction | None |

---

# Commands Reference

## Installation

```bash
uv sync                    # Install dependencies
```

## Database

```bash
uv run python data_gen/generate_australia_surfbreaks_oneshot.py  # Populate database
```

## Development

```bash
uv run uvicorn main:app --reload    # Start dev server
# Visit http://localhost:8000
```

## Testing

```bash
uv run pytest                    # Run all tests
uv run pytest path/to/test.py    # Run specific test file
uv run pytest -k "test_name"     # Run tests matching pattern
```

## Code Quality

```bash
uv run mypy .                    # Type checking
uv run ruff check .              # Linting
```

---

# License

MIT
