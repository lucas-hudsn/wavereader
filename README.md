# wave~reader

AI-powered surf forecasting for 50+ Australian surf breaks. Combines a curated SQLite database with Google Gemini AI and Open-Meteo marine/weather data to generate personalized surf reports.

## Quick Start

```bash
# Backend
uv sync
cp .env.example .env  # Add your GOOGLE_API_KEY
uv run python data_gen/generate_australia_surfbreaks_oneshot.py  # First-time DB setup
uv run uvicorn main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

**Development:** Frontend on `http://localhost:3000`, backend on `http://localhost:8000`. Vite proxies `/api/*` requests to the backend.

**Production:** Build frontend with `cd frontend && npm run build`, then run `uv run uvicorn main:app --host 0.0.0.0 --port 8000` — it serves the built React app and API together.

**Docker:**
```bash
docker build -t wavereader .
docker run -p 8000:8000 --env-file .env wavereader
```

## Requirements

- Python 3.14+
- uv package manager
- Node.js 22+
- Google Gemini API key ([get one here](https://aistudio.google.com/app/apikey))

## Features

- Browse 50+ Australian surf breaks by state
- Search and filter by state/skill level
- Save favorites (persisted in localStorage) with toast notifications
- View detailed break characteristics and ideal conditions
- Interactive 7-day wave height and wind direction charts
- AI-generated surf forecasts via Google Gemini
- Keyboard navigation (press `/` to search, `Esc` to clear)
- Dark mode (automatic, follows system preference)
- Offline detection banner
- Responsive design with mobile, tablet, and desktop breakpoints

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, SQLite (WAL mode), slowapi (rate limiting) |
| Frontend | React 19, React Router, Vite, DOMPurify |
| APIs | Google Gemini (forecasts), Open-Meteo (marine/weather) |
| Testing | pytest (backend), Vitest + Testing Library (frontend) |
| CI | GitHub Actions (lint, type check, test, build) |

## Project Structure

```
wavereader/
├── main.py                # FastAPI app (CORS, logging, rate limiting)
├── db.py                  # SQLite connection (context manager, WAL, indexes)
├── routes/                # API route handlers
│   ├── states.py          # /api/states, /api/breaks, /api/breaks/{state}
│   └── breaks.py          # /api/break/{name} (rate-limited)
├── services/              # External API integrations
│   ├── openmeteo.py       # Open-Meteo marine + weather (cached 1hr)
│   └── gemini.py          # Gemini AI forecast generation
├── tests/                 # Backend tests (pytest)
├── data/                  # SQLite database
├── data_gen/              # Database population scripts
├── frontend/              # React frontend
│   ├── src/
│   │   ├── api/           # API client
│   │   ├── components/    # Layout, BreakCard, WeatherChart, ErrorBoundary, Toast, etc.
│   │   ├── context/       # FavoritesContext (memoized, with toast)
│   │   ├── hooks/         # useBreakDetail, useBreakFilters, useOnlineStatus, useToast
│   │   ├── pages/         # Landing, BreakDetail, Favorites (lazy-loaded)
│   │   ├── utils/         # Shared formatters
│   │   ├── test/          # Frontend tests (Vitest)
│   │   └── constants.js   # Shared constants
│   └── vite.config.js     # Vite + Vitest config
├── .github/workflows/     # CI pipeline
├── Dockerfile             # Multi-stage Docker build
└── .pre-commit-config.yaml
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check (verifies DB connectivity) |
| `GET /api/states` | List all states with surf breaks |
| `GET /api/breaks?limit=50&offset=0` | Paginated list of all breaks |
| `GET /api/breaks/{state}` | List breaks for a specific state |
| `GET /api/break/{name}` | Full break details + weather + AI forecast (rate-limited, case-insensitive) |
| `GET /docs` | Interactive API documentation (Swagger UI) |

## Commands

```bash
# Backend
uv run uvicorn main:app --reload        # Dev server
uv run pytest tests/ -v                 # Run tests
uv run ruff check .                     # Lint
uv run mypy main.py routes/ services/   # Type check

# Frontend
cd frontend
npm run dev        # Dev server with HMR
npm test           # Run tests
npm run lint       # ESLint
npm run build      # Production build
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Yes | Google API key for Gemini AI forecasts |
| `GEMINI_MODEL` | No | Gemini model name (default: `gemma-3-27b-it`) |

Copy `.env.example` to `.env` and fill in your values.

---

MIT
