import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "data" / "wavereader.db"


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def serialize_row(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)
