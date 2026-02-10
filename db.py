import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "data" / "wavereader.db"


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_surf_breaks_state ON surf_breaks(state)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_surf_breaks_name ON surf_breaks(name COLLATE NOCASE)"
    )


@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


def serialize_row(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)
