# wave~reader - Agentic Surf Forecasting

An AI-powered surf forecasting application built with **LangGraph**, **FastAPI**, **Google Gemini**, and **PostgreSQL**. wave~reader uses autonomous agents to analyze surf breaks and provide comprehensive daily forecasts for 50+ Australian surf spots.

## Features

- **Multi-Agent Architecture**: LangGraph orchestrates specialized agents for different forecasting tasks
  - Description Agent: Provides surf break characteristics and wave type information
  - Coordinates Agent: Locates the surf break using AI-powered geolocation
  - Weather Agent: Fetches real-time swell and wind data from Open-Meteo
  - Forecast Agent: Generates actionable daily forecasts

- **Surf Break Database**: PostgreSQL database with 50+ Australian surf breaks including:
  - Break characteristics (reef/sand, point/beach, left/right)
  - Skill level recommendations
  - Ideal conditions (wind, tide, swell size)

- **Real-Time Weather Data**: Integrates with Open-Meteo marine API for accurate swell and wind forecasts

- **Interactive Charts**: Visualizes hourly wave height and wind speed patterns

- **Modern UI**: Retro monospace-themed interface with vanilla HTML/CSS/JavaScript

## Tech Stack

- **Backend**: FastAPI, Uvicorn
- **AI/ML**: LangGraph, Google Gemini 2.5 Pro
- **Database**: PostgreSQL
- **Frontend**: Vanilla HTML, CSS, JavaScript with Chart.js
- **APIs**: Open-Meteo (marine weather data), Google Gemini API
- **Package Manager**: uv
- **Python**: 3.14+

## Installation

### Prerequisites

- Python 3.14+
- uv package manager
- PostgreSQL
- Google Gemini API key

### Setup

1. **Clone and navigate to project**
```bash
cd wavereader
```

2. **Install dependencies with uv**
```bash
uv sync
```

3. **Set up PostgreSQL**
```bash
brew install postgresql@17
brew services start postgresql@17
export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"
createdb wavereader
```

4. **Create environment file**
```bash
cp .env.example .env
```

5. **Configure `.env`**
```
GEMINI_API_KEY=your_gemini_key_here
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=wavereader
POSTGRES_USER=your_username
POSTGRES_PASSWORD=
```

6. **Populate the database**
```bash
uv run python data_gen/generate_australia_surfbreaks_oneshot.py
```

## Running the Application

### Start the server
```bash
uv run uvicorn main:app --reload
```

The application will be available at `http://localhost:8000`

## Pages

### Landing Page (`/`)
Home page with navigation to Browse and Forecast sections.

### Browse Breaks (`/browse`)
- Select a state from the dropdown
- Choose a surf break to view details
- See break characteristics, skill level, and ideal conditions

### Live Forecast (`/forecast-chat`)
- Enter any beach name
- Get real-time conditions and AI-generated forecast
- View 24-hour wave and wind charts

## API Endpoints

### Pages
- `GET /` - Landing page
- `GET /browse` - Surf breaks browser
- `GET /forecast-chat` - Live forecast chatbot

### Data APIs
- `GET /api/states` - List all states with surf breaks
- `GET /api/breaks/{state}` - List breaks for a state
- `GET /api/break/{name}` - Get details for a specific break
- `POST /forecast` - Run the AI forecast agent
- `GET /health` - Health check

## Project Structure

```
wavereader/
├── main.py                  # FastAPI application
├── agents/
│   ├── __init__.py
│   ├── surf_graph.py        # LangGraph agent orchestration
│   └── tools.py             # Agent tools (Gemini + API integration)
├── templates/
│   ├── landing.html         # Landing page
│   ├── browse.html          # Surf breaks browser
│   └── chat.html            # Forecast chatbot
├── static/
│   ├── style.css            # Styling
│   ├── app.js               # Forecast page logic
│   └── browse.js            # Browse page logic
├── data_gen/
│   ├── generate_bellsbeach_data_zeroshot.py   # Zero-shot prompting example
│   ├── generate_australia_surfbreaks_oneshot.py  # One-shot batch generation
│   └── PROMPTING.md         # Prompt engineering documentation
├── pyproject.toml           # Dependencies
└── README.md
```

## Data Generation

The `data_gen/` folder contains scripts for generating surf break data using prompt engineering techniques:

### Zero-Shot Prompting
`generate_bellsbeach_data_zeroshot.py` - Generates data without examples, using explicit field definitions and constraints.

### One-Shot Prompting
`generate_australia_surfbreaks_oneshot.py` - Uses Bells Beach as an example to generate consistent data for 50 Australian surf breaks.

See `data_gen/PROMPTING.md` for detailed documentation on the prompt engineering techniques used.

## Agent Pipeline

When you search for a beach, the LangGraph agent orchestrates:

1. **Description Agent** - Retrieves surf break characteristics
2. **Coordinates Agent** - Obtains latitude/longitude from beach name
3. **Weather Agent** - Fetches swell and wind data from Open-Meteo
4. **Forecast Agent** - Synthesizes data into actionable advice

```
User Input (Beach Name)
    │
    ▼
LangGraph Agent Graph
    ├─ Description Agent (Gemini 2.5 Pro)
    ├─ Coordinates Agent (Gemini 2.5 Pro)
    ├─ Weather Agent (Open-Meteo API)
    └─ Forecast Agent (Gemini 2.5 Pro)
    │
    ▼
Frontend Visualization
```

## External APIs

### Google Gemini API
- Model: `gemini-2.5-pro`
- Used for: descriptions, coordinates parsing, forecast synthesis
- Requires API key in `.env`

### Open-Meteo Marine API
- Endpoint: `https://marine-api.open-meteo.com/v1/marine`
- No authentication required
- Returns hourly and daily marine forecasts

## License

MIT License
