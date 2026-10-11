"""SQLite access (DATABASE.md sections 1-4).

Single file, WAL mode, one writer (`--workers 1`). No ORM in MVP.
Callers use parameterized queries only.
"""

import os
import sqlite3

PRAGMAS = (
    "PRAGMA journal_mode=WAL;",
    "PRAGMA foreign_keys=ON;",
    "PRAGMA synchronous=NORMAL;",
    "PRAGMA busy_timeout=5000;",
)

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "db", "schema.sql")


def connect(db_path: str) -> sqlite3.Connection:
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    for pragma in PRAGMAS:
        conn.execute(pragma)
    return conn


def init_schema(db_path: str) -> None:
    if not os.path.isfile(SCHEMA_FILE):
        raise FileNotFoundError("schema.sql not found at " + SCHEMA_FILE)
    with open(SCHEMA_FILE, "r", encoding="utf-8") as fh:
        schema_sql = fh.read()
    conn = connect(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()


def check_db(db_path: str) -> bool:
    """Cheap liveness probe for /healthz. True iff a query succeeds."""
    try:
        conn = connect(db_path)
        try:
            conn.execute("SELECT 1").fetchone()
            return True
        finally:
            conn.close()
    except Exception:
        return False
