import json
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL DEFAULT 'google',
    scopes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_sync TIMESTAMP,
    deleted_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS canvas_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canvas_url TEXT NOT NULL,
    session_cookies TEXT NOT NULL,
    last_sync TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'active',
    deleted_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER REFERENCES accounts(id),
    source TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    all_day INTEGER DEFAULT 0,
    recurring_rule TEXT,
    location TEXT,
    event_type TEXT,
    raw_data TEXT,
    synced_at TIMESTAMP,
    UNIQUE(source, external_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    course TEXT,
    deadline TIMESTAMP,
    estimated_minutes INTEGER,
    priority INTEGER DEFAULT 3,
    status TEXT NOT NULL DEFAULT 'pending',
    grade_weight REAL,
    current_grade TEXT,
    ai_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(source, external_id)
);

CREATE TABLE IF NOT EXISTS schedule_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id),
    date DATE NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    block_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    ai_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_block_id INTEGER REFERENCES schedule_blocks(id),
    task_id INTEGER REFERENCES tasks(id),
    remind_at TIMESTAMP NOT NULL,
    reminder_type TEXT NOT NULL,
    message TEXT NOT NULL,
    urgent INTEGER DEFAULT 0,
    fired INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS ai_context_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    context_hash TEXT,
    schedule_json TEXT,
    tokens_used INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class PlannerDB:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        conn = self._get_conn()
        conn.executescript(SCHEMA_SQL)
        cursor = conn.execute("SELECT COUNT(*) FROM schema_version")
        if cursor.fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def set_preference(self, key: str, value: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO preferences (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()

    def get_preference(self, key: str, default: str | None = None) -> str | None:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT value FROM preferences WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row[0] if row else default

    def get_all_preferences(self) -> dict[str, str]:
        conn = self._get_conn()
        cursor = conn.execute("SELECT key, value FROM preferences")
        return {row[0]: row[1] for row in cursor.fetchall()}

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
