# SmartSurf - Agentic Surf Forecasting Website

An AI-powered surf forecasting application built with **LangGraph**, **FastAPI**, and **Open-Meteo API**. SmartSurf uses autonomous agents to analyze surf breaks and provide comprehensive daily forecasts.

## 🌊 Features

- **Multi-Agent Architecture**: LangGraph orchestrates specialized agents for different forecasting tasks
  - Description Agent: Provides surf break characteristics and wave type information
  - Coordinates Agent: Locates the surf break using AI-powered geolocation
  - Weather Agent: Fetches real-time swell and wind data from Open-Meteo
  - Forecast Agent: Generates actionable daily forecasts

- **Real-Time Weather Data**: Integrates with Open-Meteo marine API for accurate swell and wind forecasts
- **Interactive Charts**: Visualizes hourly wave height and wind speed patterns
- **Modern UI**: Beautiful dark-themed interface with vanilla HTML/CSS and vanilla JavaScript
- **Fast & Responsive**: Built on FastAPI with server-side async operations

## 🛠️ Tech Stack

- **Backend**: FastAPI, Uvicorn
- **AI/ML**: LangGraph, LangChain, OpenAI GPT-4o-mini
- **Frontend**: Vanilla HTML, CSS, JavaScript with Chart.js
- **APIs**: Open-Meteo (marine weather data)
- **Package Manager**: uv
- **Python**: 3.14+

## 📦 Installation

### Prerequisites

- Python 3.14+
- uv package manager
- OpenAI API key

### Setup

1. **Clone and navigate to project**
```bash
cd /Users/lucashudson/Desktop/projects/smartsurf
```

2. **Install dependencies with uv**
```bash
uv sync
```

3. **Create environment file**
```bash
cp .env.example .env
```

4. **Add your OpenAI API key to `.env`**
```
OPENAI_API_KEY=your_key_here
```

## 🚀 Running the Application

### Start the server
```bash
uv run uvicorn main:app --reload
```

The application will be available at `http://localhost:8000`

### Using with different configurations
```bash
# Custom host and port
uv run uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

## 📋 How It Works

### Agent Pipeline

When you search for a beach, the LangGraph agent orchestrates the following workflow:

1. **Description Agent** → Retrieves detailed information about the surf break (wave type, conditions, skill level suitability)
2. **Coordinates Agent** → Uses LLM to obtain precise latitude/longitude from the beach name
3. **Weather Agent** → Fetches current/forecasted swell height, period, wind speed, and direction from Open-Meteo
4. **Forecast Agent** → Synthesizes all data into actionable forecasting advice with:
   - Overall conditions summary
   - Best times to surf
   - Skill level recommendations
   - Hazards and considerations
   - Equipment suggestions

### Data Flow

```
User Input (Beach Name)
    ↓
LangGraph Agent Graph
    ├→ Description Agent (LLM)
    ├→ Coordinates Agent (LLM + JSON parsing)
    ├→ Weather Agent (Open-Meteo API)
    └→ Forecast Agent (LLM synthesis)
    ↓
FastAPI Endpoint
    ↓
Frontend Visualization (Charts + Summary)
```

## 🎨 UI Components

- **Search Bar**: Enter any beach name worldwide
- **Loading Indicator**: Animated spinner during agent execution
- **Info Card**: Beach name, description, and exact coordinates
- **Weather Card**: Current conditions (wave height, period, wind)
- **Chart**: Hourly wave and wind patterns over 24 hours
- **Forecast Card**: AI-generated daily forecast with specific recommendations

## 🔧 Project Structure

```
smartsurf/
├── main.py                  # FastAPI application
├── agents/
│   ├── __init__.py
│   ├── surf_graph.py       # LangGraph agent orchestration
│   └── tools.py            # Agent tools (LLM calls + API integration)
├── templates/
│   └── index.html          # Main UI template
├── static/
│   ├── style.css           # Styling (dark theme)
│   └── app.js              # Frontend logic + Chart.js
├── pyproject.toml          # Dependencies
├── .env.example            # Configuration template
└── README.md               # This file
```

## 🌐 API Endpoints

### GET `/`
Returns the main HTML interface

### POST `/forecast`
Executes the surf forecasting agent
- **Request**: `{"beach": "Bells Beach"}`
- **Response**:
```json
{
  "beach_name": "Bells Beach",
  "description": "Famous right-hand point break...",
  "coordinates": {
    "latitude": -38.3587,
    "longitude": 144.4217
  },
  "weather_data": {
    "wave_height_max": 1.5,
    "wave_period_max": 8.0,
    "wind_speed_max": 15.0,
    "wind_direction": 180,
    "hourly": {...}
  },
  "forecast": "Forecast summary...",
  "success": true
}
```

### GET `/health`
Health check endpoint

## 🧠 Using LangGraph Effectively

The application uses LangGraph's `StateGraph` to manage the agent pipeline:

- **State**: Typed dictionary tracking beach info, description, coordinates, weather, and forecast
- **Nodes**: Each agent is a node that processes and updates state
- **Edges**: Define the execution flow (sequential in this case)
- **Compilation**: Graph is compiled and invoked synchronously/asynchronously

Benefits:
- Clear agent responsibilities
- Easy to debug each step
- Extensible for additional agents
- Deterministic execution order

## 🔌 API Integrations

### Open-Meteo Marine API
- Endpoint: `https://marine-api.open-meteo.com/v1/marine`
- No authentication required
- Returns hourly and daily marine forecasts
- Data includes: wave height, period, direction, wind speed/direction

### OpenAI API
- Model: `gpt-4o-mini`
- Used for: descriptions, coordinates parsing, forecast synthesis
- Requires valid API key in `.env`

## 🎯 Example Usage

1. Open `http://localhost:8000`
2. Enter a beach name: "Pipeline" or "Sunset Beach"
3. Click "Get Forecast"
4. View:
   - Beach description and location
   - Current weather conditions
   - 24-hour wave/wind chart
   - Detailed daily forecast

## 🐛 Troubleshooting

### "OPENAI_API_KEY not set"
Ensure you've created `.env` file with your API key:
```
OPENAI_API_KEY=sk-...
```

### Coordinates returning (0, 0)
The LLM may struggle with uncommon beach names. Try:
- Full beach name with location
- More famous breaks (Bells Beach, Pipeline, Malibu)

### Chart not rendering
Ensure Chart.js loads properly. Check browser console for errors.

### Slow responses
LLM calls can take 2-5 seconds. This is normal. Consider caching results for popular beaches.

## 🚀 Future Enhancements

- Caching popular beach forecasts
- Historical data and trends
- Multi-day forecasts
- Swell prediction models
- Beach-specific hazard warnings
- User preferences and saved beaches
- Social sharing of forecasts

## 📄 License

MIT License - Feel free to use and modify for your projects

## 🤝 Contributing

Contributions welcome! Submit issues and pull requests to improve SmartSurf.

---

Built with ❤️ using LangGraph, FastAPI, and Open-Meteo API


A project created with FastAPI CLI.

## Quick Start

### Start the development server

```bash
uv run fastapi dev
```

Visit http://localhost:8000

### Deploy to FastAPI Cloud

> FastAPI Cloud is currently in private beta. Join the waitlist at https://fastapicloud.com

```bash
uv run fastapi login
uv run fastapi deploy
```

## Project Structure

- `main.py` - Your FastAPI application
- `pyproject.toml` - Project dependencies

## Learn More

- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [FastAPI Cloud](https://fastapicloud.com)
