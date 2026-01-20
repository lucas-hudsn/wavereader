# wave~reader

AI-powered surf forecasting for 50+ Australian surf breaks. Combines a curated SQLite database with Google Gemini AI and Open-Meteo marine/weather data to generate personalized surf reports.

## Quick Start

```bash
uv sync
cp .env.example .env  # Add your GEMINI_API_KEY
uv run python data_gen/generate_australia_surfbreaks_oneshot.py
uv run uvicorn main:app --reload
```

Visit `http://localhost:8000`

## Requirements

- Python 3.14+
- uv package manager
- Google Gemini API key

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, Jinja2, SQLite |
| Frontend | Vanilla JavaScript, CSS, SVG charts |
| APIs | Google Gemini (forecasts), Open-Meteo (marine/weather) |

## Project Structure

```
wavereader/
├── main.py              # FastAPI app (API routes & business logic)
├── data/                # SQLite database
├── data_gen/            # Data generation scripts
├── templates/           # Jinja2 HTML templates
└── static/              # CSS & JavaScript files
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/states` | List all states with surf breaks |
| `GET /api/breaks/{state}` | List breaks for a state |
| `GET /api/break/{name}` | Full break details + weather + AI forecast |
| `GET /{state}/{break_name}` | Surf break details page |

## Commands

```bash
uv run uvicorn main:app --reload    # Start dev server
uv run python data_gen/generate_australia_surfbreaks_oneshot.py  # Populate DB
uv run pytest                       # Run tests
uv run mypy .                       # Type checking
uv run ruff check .                 # Linting
uv run ruff format .                # Formatting
```

## Features

- Browse 50+ Australian surf breaks by state
- View detailed break characteristics (wave direction, bottom type, skill level)
- Weekly wave height and wind charts (SVG)
- AI-generated surf forecasts via Google Gemini
- Responsive retro monospace design

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key (required) |

---

MIT
