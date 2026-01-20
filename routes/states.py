from fastapi import APIRouter
from fastapi.responses import JSONResponse
from db import get_db_connection, serialize_row

router = APIRouter(tags=["states"])


@router.get("/api/states")
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


@router.get("/api/breaks")
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


@router.get("/api/breaks/{state}")
async def get_breaks_by_state(state: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM surf_breaks WHERE state = ? ORDER BY name", (state,)
        )
        breaks = [row["name"] for row in cursor.fetchall()]
        conn.close()
        return JSONResponse({"breaks": breaks})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
