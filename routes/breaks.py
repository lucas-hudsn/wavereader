from fastapi import APIRouter
from fastapi.responses import JSONResponse
from db import get_db_connection, serialize_row
from services.openmeteo import query_openmeteo
from services.gemini import generate_forecast

router = APIRouter(tags=["breaks"])


@router.get("/api/break/{name}")
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
