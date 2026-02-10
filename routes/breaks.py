import asyncio
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from db import get_db, serialize_row
from services.gemini import generate_forecast
from services.openmeteo import query_openmeteo

router = APIRouter(tags=["breaks"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/api/break/{name}")
@limiter.limit("10/minute")
async def get_break_details(request: Request, name: str):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT name, description, state, latitude, longitude,
                          wave_direction, bottom_type, break_type, skill_level,
                          ideal_wind, ideal_tide, ideal_swell_size
                   FROM surf_breaks WHERE name = ? COLLATE NOCASE""",
                (name,),
            )
            row = cursor.fetchone()
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail="Database error") from e

    if not row:
        raise HTTPException(status_code=404, detail="Surf break not found")

    break_info = serialize_row(row)
    latitude = break_info.get("latitude")
    longitude = break_info.get("longitude")

    if latitude and longitude:
        try:
            weather_data = await asyncio.to_thread(query_openmeteo, latitude, longitude)
        except Exception:
            weather_data = {"success": False}

        if weather_data.get("success"):
            try:
                forecast = await asyncio.to_thread(
                    generate_forecast, break_info, weather_data
                )
            except Exception:
                forecast = ""
            break_info["weather_data"] = weather_data
            break_info["forecast"] = forecast

    return break_info
