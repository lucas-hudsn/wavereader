import sqlite3

from fastapi import APIRouter, HTTPException, Query

from db import get_db, serialize_row

router = APIRouter(tags=["states"])


@router.get("/api/states")
async def get_states():
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT state FROM surf_breaks ORDER BY state")
            states = [row["state"] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail="Database error") from e
    return {"states": states}


@router.get("/api/breaks")
async def get_all_breaks(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, state, latitude, longitude, skill_level "
                "FROM surf_breaks ORDER BY state, name LIMIT ? OFFSET ?",
                (limit, offset),
            )
            breaks = [serialize_row(row) for row in cursor.fetchall()]

            cursor.execute("SELECT COUNT(*) as total FROM surf_breaks")
            total = cursor.fetchone()["total"]
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail="Database error") from e
    return {"breaks": breaks, "total": total, "limit": limit, "offset": offset}


@router.get("/api/breaks/{state}")
async def get_breaks_by_state(state: str):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM surf_breaks WHERE state = ? ORDER BY name",
                (state,),
            )
            breaks = [row["name"] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail="Database error") from e
    return {"breaks": breaks}
