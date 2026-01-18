from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import os
from decimal import Decimal
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from dotenv import load_dotenv
from agents.surf_graph import run_surf_forecast_agent

load_dotenv()


def serialize_row(row: dict) -> dict:
    """Convert Decimal values to float for JSON serialization"""
    return {
        key: float(value) if isinstance(value, Decimal) else value
        for key, value in row.items()
    }

# Setup
app = FastAPI()
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def get_db_connection():
    """Get a database connection"""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        database=os.getenv("POSTGRES_DB", "wavereader"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        cursor_factory=RealDictCursor,
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the landing page"""
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/forecast-chat", response_class=HTMLResponse)
async def forecast_chat(request: Request):
    """Render the chatbot forecast page"""
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/browse", response_class=HTMLResponse)
async def browse(request: Request):
    """Render the surf breaks browser page"""
    return templates.TemplateResponse("browse.html", {"request": request})


@app.get("/api/states")
async def get_states():
    """Get all unique states from surf breaks"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT state FROM surf_breaks ORDER BY state")
        states = [row["state"] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return JSONResponse({"states": states})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/breaks/{state}")
async def get_breaks_by_state(state: str):
    """Get all surf breaks for a given state"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM surf_breaks WHERE state = %s ORDER BY name",
            (state,)
        )
        breaks = [row["name"] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return JSONResponse({"breaks": breaks})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/break/{name}")
async def get_break_details(name: str):
    """Get details for a specific surf break"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT name, description, state, latitude, longitude,
                      wave_direction, bottom_type, break_type, skill_level,
                      ideal_wind, ideal_tide, ideal_swell_size
               FROM surf_breaks WHERE name = %s""",
            (name,)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return JSONResponse({"error": "Surf break not found"}, status_code=404)

        return JSONResponse(serialize_row(dict(row)))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/forecast")
async def forecast(request: Request):
    """Run the surf forecast agent for a given beach"""
    data = await request.json()
    beach = data.get("beach", "").strip()

    if not beach:
        return JSONResponse({"error": "Beach name required"}, status_code=400)

    try:
        result = await run_surf_forecast_agent(beach)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok"}
