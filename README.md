# wave~reader

AI-powered surf forecasting for 50+ Australian surf breaks. Combines a curated SQLite database with Google Gemini AI and Open-Meteo marine/weather data to generate personalized surf reports.

## Quick Start

```bash
# Backend
uv sync
cp .env.example .env  # Add your GOOGLE_API_KEY
uv run python data_gen/generate_australia_surfbreaks_oneshot.py
uv run uvicorn main:app --reload

# Frontend (development)
cd frontend
npm install
npm run dev
```

**Development:** Frontend runs on `http://localhost:3000`, backend on `http://localhost:8000`

**Production:** Build frontend with `npm run build`, then run backend - it serves the built React app.

## Requirements

- Python 3.14+
- uv package manager
- Node.js 18+
- Google Gemini API key

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, SQLite |
| Frontend | React, React Router, Vite |
| APIs | Google Gemini (forecasts), Open-Meteo (marine/weather) |

## Project Structure

```
wavereader/
├── main.py              # FastAPI app
├── routes/              # API route handlers
├── services/            # External API integrations
├── data/                # SQLite database
├── data_gen/            # Data generation scripts
└── frontend/            # React frontend
    ├── src/
    │   ├── components/  # Reusable UI components
    │   ├── pages/       # Route pages
    │   ├── context/     # React context (favorites)
    │   └── api/         # API client
    └── dist/            # Production build
```

## Features

- Browse 50+ Australian surf breaks by state
- Search and filter by state/skill level
- Save favorites (persisted in localStorage)
- View detailed break characteristics
- Interactive 7-day wave height and wind charts
- AI-generated surf forecasts via Google Gemma
- Keyboard navigation (press `/` to search)
- Responsive retro monospace design

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/states` | List all states with surf breaks |
| `GET /api/breaks` | List all breaks with basic info |
| `GET /api/breaks/{state}` | List breaks for a state |
| `GET /api/break/{name}` | Full break details + weather + AI forecast |

## Commands

```bash
# Backend
uv run uvicorn main:app --reload    # Start dev server
uv run python data_gen/generate_australia_surfbreaks_oneshot.py  # Populate DB

# Frontend
cd frontend
npm run dev      # Development server with HMR
npm run build    # Production build
npm run preview  # Preview production build
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GOOGLE_API_KEY` | Google API key (required for AI forecasts) |

---

MIT
