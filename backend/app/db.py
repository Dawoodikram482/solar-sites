"""Database access: one SQLite file, plain SQL, no ORM.

Why plain sqlite3: it ships with Python (no extra dependency), the whole schema
fits on one screen, and every query is visible in the code. All queries use
"?" placeholders, so user input is never pasted into SQL (no SQL injection).
"""

import os
import sqlite3
from collections.abc import Iterator

# Where the database file lives. In Docker this is /app/data/solar.db.
# Tests point it at a temporary file via the same environment variable.
DB_PATH = os.environ.get("DATABASE_PATH", "data/solar.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,      -- stored lower-case
    password_hash TEXT    NOT NULL,             -- scrypt hash, never the password
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT    PRIMARY KEY,             -- SHA-256 of the cookie value
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token TEXT    NOT NULL,
    expires_at TEXT    NOT NULL                 -- ISO timestamp, UTC
);

CREATE TABLE IF NOT EXISTS sites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_name TEXT    NOT NULL,
    address     TEXT    NOT NULL,
    latitude    REAL    NOT NULL,
    longitude   REAL    NOT NULL,
    roof_area_m2 REAL,                          -- optional in the API contract
    peak_kwp    REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sites_user ON sites(user_id);
"""


def connect() -> sqlite3.Connection:
    """Open a connection. Rows behave like dicts (row["email"])."""
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    # check_same_thread=False: FastAPI may open the connection in one worker
    # thread and run the route in another. That is safe here because each
    # connection belongs to exactly one request and is never shared.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # SQLite ignores foreign keys unless you switch them on per connection.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the tables if they do not exist yet. Called once at startup."""
    with connect() as conn:
        conn.executescript(SCHEMA)


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: a fresh connection per request, closed afterwards.

    `with conn:` commits when the request handler finishes without an error
    and rolls back if it raised, so a half-finished request never leaves
    half-written data behind.
    """
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()
