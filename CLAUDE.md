# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Wavereader is an AI-powered surf forecasting app for 50+ Australian surf breaks. It combines a SQLite database of break characteristics with Google Gemini AI and Open-Meteo weather/marine data to generate personalized daily surf reports.

## Commands

### Backend (Python/FastAPI)
```bash
uv sync                                # Install dependencies
uv run uvicorn main:app --reload       # Dev server on :8000
uv run pytest tests/ -v                # Run backend tests
uv run ruff check .                    # Lint Python code
uv run ruff check --fix .              # Auto-fix lint issues
uv run mypy main.py routes/ services/ db.py  # Type check
uv run python data_gen/generate_australia_surfbreaks_oneshot.py  # Populate DB (first-time setup)
```

### Frontend (React/Vite)
```bash
cd frontend
npm install        # Install dependencies
npm run dev        # Dev server on :3000 (proxies /api/* to :8000)
npm run build      # Production build to frontend/dist/
npm run lint       # ESLint
npm test           # Run Vitest tests
npm run test:watch # Vitest in watch mode
```

### Production
```bash
cd frontend && npm run build   # Build frontend assets
uv run uvicorn main:app --host 0.0.0.0 --port 8000  # Serves both API and frontend
```

### Docker
```bash
docker build -t wavereader .
docker run -p 8000:8000 --env-file .env wavereader
```

## Architecture

**Backend:** FastAPI app (`main.py`) with two route modules, two service modules, CORS, rate limiting, and request logging.

- `routes/states.py` — `/api/states`, `/api/breaks` (paginated), `/api/breaks/{state}` endpoints
- `routes/breaks.py` — `/api/break/{name}` (case-insensitive, rate-limited) fetches weather + AI forecast
- `services/openmeteo.py` — Queries Open-Meteo marine + weather APIs, 1-hour cache per coordinate
- `services/gemini.py` — Sends break info + weather summary to Gemini, configurable model via `GEMINI_MODEL` env var
- `db.py` — SQLite with context managers, WAL mode, indexes on `state` and `name`

**Frontend:** React 19 SPA with React Router, built with Vite. Lazy-loaded routes, error boundaries, DOMPurify for XSS protection.

- `frontend/src/api/index.js` — API client (fetch wrapper for `/api/*` endpoints)
- `frontend/src/constants.js` — Shared constants (API_BASE, STORAGE_KEY, SKILL_LEVELS)
- `frontend/src/utils/formatters.js` — Shared utility functions (capitalize)
- `frontend/src/context/FavoritesContext.jsx` — Memoized favorites state via React Context + localStorage + toast notifications
- `frontend/src/hooks/` — Custom hooks: `useBreakDetail`, `useBreakFilters`, `useOnlineStatus`
- `frontend/src/pages/` — Landing (browse/filter), BreakDetail (forecast + charts), Favorites
- `frontend/src/components/` — Layout, BreakCard (uses `<Link>`), SearchBar (labeled), ErrorBoundary, Toast, WeatherChart (memoized), Skeleton

**Data flow:** Frontend → Vite proxy (dev) or FastAPI catch-all (prod) → FastAPI routes → SQLite + Open-Meteo + Gemini → JSON response → React renders with interactive charts.

## Key Details

- **Python 3.14+** required, managed with `uv`
- **Environment variables:** `GOOGLE_API_KEY` in `.env` (required), `GEMINI_MODEL` (optional, defaults to `gemma-3-27b-it`). See `.env.example` for template.
- **Database:** SQLite at `data/wavereader.db` with WAL mode and indexes. Schema has `surf_breaks` table with columns: id, name, description, state, latitude, longitude, wave_direction, bottom_type, break_type, skill_level, ideal_wind, ideal_tide, ideal_swell_size, created_at
- **Dev setup:** Run backend on :8000 and frontend on :3000 simultaneously; Vite proxies API calls
- **Production:** `npm run build` outputs to `frontend/dist/`; FastAPI serves static assets and falls back to `index.html` for SPA routing
- **Testing:** Backend uses pytest with FastAPI TestClient; Frontend uses Vitest + Testing Library
- **Linting:** ruff (Python), ESLint (frontend), configured in `pyproject.toml` and `eslint.config.js`
- **CI:** GitHub Actions workflow in `.github/workflows/ci.yml` runs lint, type check, tests, and build
- **Rate limiting:** `/api/break/{name}` is rate-limited to 10 requests/minute per IP via slowapi
- **Dark mode:** Automatic via `prefers-color-scheme` CSS media query
