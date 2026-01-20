# AGENTS.md - wave~reader Development Guide

This document provides guidelines for AI agents working on the wave~reader codebase.

## Project Overview

wave~reader is an AI-powered surf forecasting web application for Australian surf breaks. Stack:
- **Backend**: Python 3.14+, FastAPI, Jinja2 templates, SQLite
- **Frontend**: Vanilla JavaScript, CSS with CSS variables, SVG charts
- **APIs**: Google Gemini (forecasts), Open-Meteo (weather/marine data)
- **Package Manager**: uv

## Build/Lint/Test Commands

```bash
# Install dependencies
uv sync

# Run development server (with auto-reload)
uv run uvicorn main:app --reload

# Run with custom host/port
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Type checking
uv run mypy .

# Linting
uv run ruff check .

# Format code
uv run ruff format .

# Run all tests
uv run pytest

# Run specific test file
uv run pytest path/to/test.py

# Run tests matching pattern
uv run pytest -k "test_name"

# Populate database with surf breaks
uv run python data_gen/generate_australia_surfbreaks_oneshot.py
```

## Code Style Guidelines

### Python (main.py, data_gen/)

**Imports**: Group imports in this order: stdlib, third-party, local
```python
import os
from pathlib import Path
from fastapi import FastAPI, Request
from dotenv import load_dotenv
from google import genai
```

**Naming Conventions**:
- Variables/functions: `snake_case` (e.g., `get_db_connection`, `wave_height_max`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `REPORT_MODEL`, `DB_PATH`)
- Classes: `PascalCase`
- Private helpers: Leading underscore (e.g., `_helper_function`)

**Type Hints**: Always use type hints for function signatures
```python
def query_openmeteo(latitude: float, longitude: float) -> dict:
    ...
```

**Error Handling**: Use try/except with JSONResponse for errors
```python
try:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ...")
    results = cursor.fetchall()
except Exception as e:
    return JSONResponse({"error": str(e)}, status_code=500)
finally:
    conn.close()
```

**Database**: Use `get_db_connection()` helper, always close connections
```python
def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn
```

### JavaScript (static/*.js)

**Naming**: camelCase for variables/functions
```javascript
const loadingSpinner = document.getElementById('loadingSpinner');
```

**Async/Await**: Prefer async/await over raw promises
```javascript
async function loadBreakDetails() {
    try {
        const response = await fetch(`/api/break/${encodeURIComponent(breakName)}`);
        const data = await response.json();
        return data;
    } catch (error) {
        showError('Failed to load break details');
    }
}
```

**URL Encoding**: Always use `encodeURIComponent()` for dynamic segments
```javascript
fetch(`/api/breaks/${encodeURIComponent(state)}`)
window.location.href = `/${encodeURIComponent(state)}/${encodeURIComponent(breakName)}`;
```

### CSS (static/style.css)

**CSS Variables**: Define all colors/spacing in `:root`
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

**Naming**: kebab-case for class names
```css
.break-details, .loading-spinner, .forecast-card
```

## Architecture Patterns

### Request Flow
User request → FastAPI route → SQLite query → Open-Meteo APIs → Gemini AI → JSON/HTML response

### API Endpoints
- `GET /api/states` - List all states with surf breaks
- `GET /api/breaks/{state}` - List breaks for a state
- `GET /api/break/{name}` - Full break details + weather + forecast
- `GET /{state}/{break_name}` - Surf break page

### Database
- SQLite at `data/wavereader.db`
- Table: `surf_breaks` with break characteristics
- Use `get_db_connection()` for all queries

## Environment Variables

Required: `GEMINI_API_KEY` - Google Gemini API key for AI forecasts

## Code Review Checklist

- [ ] Type hints present on all Python functions
- [ ] Error handling with try/except where appropriate
- [ ] Database connections properly closed
- [ ] URL parameters properly encoded
- [ ] CSS variables used instead of hardcoded values
- [ ] No comments added (unless explicitly requested)
- [ ] Consistent naming convention throughout
- [ ] Imports organized (stdlib, third-party, local)
