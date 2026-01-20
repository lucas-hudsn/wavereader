import os
from decimal import Decimal
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv
import sqlite3
import requests
from google import genai

load_dotenv()

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "wavereader.db"

app = FastAPI()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

GEMINI_CLIENT = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
REPORT_MODEL = "gemma-3-27b-it"


def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def serialize_row(row: sqlite3.Row) -> dict:
    return dict(row)


def query_openmeteo(latitude: float, longitude: float) -> dict:
    marine_url = "https://marine-api.open-meteo.com/v1/marine"
    marine_params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ["wave_height", "wave_period", "wave_direction"],
        "daily": ["wave_height_max", "wave_period_max"],
        "timezone": "auto",
        "forecast_days": 7,
    }

    weather_url = "https://api.open-meteo.com/v1/forecast"
    weather_params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ["wind_speed_10m", "wind_direction_10m"],
        "daily": ["wind_speed_10m_max", "wind_direction_10m_dominant"],
        "timezone": "auto",
        "forecast_days": 7,
    }

    marine_response = requests.get(marine_url, params=marine_params, timeout=10)
    marine_response.raise_for_status()
    marine_data = marine_response.json()

    weather_response = requests.get(weather_url, params=weather_params, timeout=10)
    weather_response.raise_for_status()
    weather_data = weather_response.json()

    marine_daily = marine_data.get("daily", {})
    weather_daily = weather_data.get("daily", {})

    return {
        "success": True,
        "latitude": latitude,
        "longitude": longitude,
        "wave_height_max": marine_daily.get("wave_height_max", [None])[0],
        "wave_period_max": marine_daily.get("wave_period_max", [None])[0],
        "wind_speed_max": weather_daily.get("wind_speed_10m_max", [None])[0],
        "wind_direction": weather_daily.get("wind_direction_10m_dominant", [None])[0],
        "hourly": {
            "time": marine_data.get("hourly", {}).get("time", []),
            "wave_height": marine_data.get("hourly", {}).get("wave_height", []),
            "wave_period": marine_data.get("hourly", {}).get("wave_period", []),
            "wave_direction": marine_data.get("hourly", {}).get("wave_direction", []),
            "wind_speed": weather_data.get("hourly", {}).get("wind_speed_10m", []),
            "wind_direction": weather_data.get("hourly", {}).get("wind_direction_10m", []),
        },
        "timezone": marine_data.get("timezone", "UTC"),
    }


def generate_forecast(break_info: dict, weather_data: dict) -> str:
    hourly = weather_data.get("hourly", {})
    times = hourly.get("time", [])
    wave_heights = hourly.get("wave_height", [])
    wind_speeds = hourly.get("wind_speed", [])

    daily_summary = []
    for day in range(7):
        start_idx = day * 24
        end_idx = start_idx + 24
        if start_idx >= len(times):
            break
        day_waves = wave_heights[start_idx:end_idx]
        day_winds = wind_speeds[start_idx:end_idx]
        day_date = times[start_idx][:10] if start_idx < len(times) else f"Day {day + 1}"
        max_wave = max(day_waves) if day_waves else 0
        avg_wind = sum(day_winds) / len(day_winds) if day_winds else 0
        daily_summary.append(f"- {day_date}: Max wave {max_wave:.1f}m, Avg wind {avg_wind:.0f}km/h")

    daily_conditions = "\n".join(daily_summary) if daily_summary else "No daily data available"

    prompt = f"""Generate a daily surf report for {break_info.get('name', 'this break')}:

SURF BREAK INFORMATION:
- Name: {break_info.get('name', 'Unknown')}
- Description: {break_info.get('description', 'No description')}
- Break Type: {break_info.get('break_type', 'Unknown')}
- Bottom Type: {break_info.get('bottom_type', 'Unknown')}
- Wave Direction: {break_info.get('wave_direction', 'Unknown')}
- Skill Level: {break_info.get('skill_level', 'Unknown')}
- Ideal Wind: {break_info.get('ideal_wind', 'Unknown')}
- Ideal Tide: {break_info.get('ideal_tide', 'Unknown')}
- Ideal Swell Size: {break_info.get('ideal_swell_size', 'Unknown')}

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

    response = GEMINI_CLIENT.models.generate_content(
        model=REPORT_MODEL,
        contents=prompt,
    )
    return response.text


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


@app.get("/api/breaks")
async def get_all_breaks():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, state, latitude, longitude, skill_level FROM surf_breaks ORDER BY state, name"
        )
        breaks = [serialize_row(row) for row in cursor.fetchall()]
        conn.close()
        return JSONResponse({"breaks": breaks})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/breaks/{state}")
async def get_breaks_by_state(state: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM surf_breaks WHERE state = ? ORDER BY name", (state,))
        breaks = [row["name"] for row in cursor.fetchall()]
        conn.close()
        return JSONResponse({"breaks": breaks})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/break/{name}")
async def get_break_details(name: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT name, description, state, latitude, longitude,
                      wave_direction, bottom_type, break_type, skill_level,
                      ideal_wind, ideal_tide, ideal_swell_size
               FROM surf_breaks WHERE name = ?""",
            (name,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return JSONResponse({"error": "Surf break not found"}, status_code=404)

        break_info = serialize_row(row)

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


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/{state}/{break_name}", response_class=HTMLResponse)
async def get_break_page(request: Request, state: str, break_name: str):
    return templates.TemplateResponse(
        "break.html", {"request": request, "state": state, "break_name": break_name}
    )
