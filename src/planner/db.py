import json
import sqlite3
from datetime import datetime, timezone
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
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
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

    # --- Account CRUD ---

    def add_account(self, email: str, provider: str = "google", scopes: str = "") -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id FROM accounts WHERE email = ? AND deleted_at IS NULL", (email,)
        )
        row = cursor.fetchone()
        if row:
            return row[0]
        cursor = conn.execute(
            "INSERT INTO accounts (email, provider, scopes) VALUES (?, ?, ?)",
            (email, provider, scopes),
        )
        conn.commit()
        return cursor.lastrowid

    def get_account(self, account_id: int) -> dict | None:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = cursor.fetchone()
        conn.row_factory = None
        return dict(row) if row else None

    def list_accounts(self) -> list[dict]:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM accounts WHERE deleted_at IS NULL ORDER BY email"
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.row_factory = None
        return rows

    def soft_delete_account(self, account_id: int) -> None:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE accounts SET deleted_at = ? WHERE id = ?", (now, account_id)
        )
        conn.commit()

    def update_account_last_sync(self, account_id: int, timestamp: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE accounts SET last_sync = ? WHERE id = ?", (timestamp, account_id)
        )
        conn.commit()

    # --- Event CRUD ---

    def upsert_event(
        self,
        account_id: int,
        source: str,
        external_id: str,
        title: str,
        start_time: str | None = None,
        end_time: str | None = None,
        all_day: bool = False,
        description: str | None = None,
        location: str | None = None,
        event_type: str | None = None,
        recurring_rule: str | None = None,
        raw_data: str | None = None,
    ) -> int:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "SELECT id FROM events WHERE source = ? AND external_id = ?",
            (source, external_id),
        )
        row = cursor.fetchone()
        if row:
            conn.execute(
                """UPDATE events SET title=?, description=?, start_time=?, end_time=?,
                   all_day=?, location=?, event_type=?, recurring_rule=?, raw_data=?, synced_at=?
                   WHERE id=?""",
                (title, description, start_time, end_time, int(all_day),
                 location, event_type, recurring_rule, raw_data, now, row[0]),
            )
            conn.commit()
            return row[0]
        cursor = conn.execute(
            """INSERT INTO events (account_id, source, external_id, title, description,
               start_time, end_time, all_day, location, event_type, recurring_rule, raw_data, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (account_id, source, external_id, title, description, start_time, end_time,
             int(all_day), location, event_type, recurring_rule, raw_data, now),
        )
        conn.commit()
        return cursor.lastrowid

    def get_events(
        self,
        source: str | None = None,
        start_after: str | None = None,
        end_before: str | None = None,
    ) -> list[dict]:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM events WHERE 1=1"
        params: list = []
        if source:
            query += " AND source = ?"
            params.append(source)
        if start_after:
            query += " AND start_time >= ?"
            params.append(start_after)
        if end_before:
            query += " AND start_time < ?"
            params.append(end_before)
        query += " ORDER BY start_time"
        cursor = conn.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.row_factory = None
        return rows

    def delete_events_for_account(self, account_id: int) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM events WHERE account_id = ?", (account_id,))
        conn.commit()

    # --- Canvas Config CRUD ---

    def add_canvas_config(self, canvas_url: str, session_cookies: str) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO canvas_configs (canvas_url, session_cookies) VALUES (?, ?)",
            (canvas_url, session_cookies),
        )
        conn.commit()
        return cursor.lastrowid

    def get_canvas_config(self, config_id: int) -> dict | None:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM canvas_configs WHERE id = ?", (config_id,))
        row = cursor.fetchone()
        conn.row_factory = None
        return dict(row) if row else None

    def list_canvas_configs(self) -> list[dict]:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM canvas_configs WHERE deleted_at IS NULL ORDER BY canvas_url"
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.row_factory = None
        return rows

    def soft_delete_canvas_config(self, config_id: int) -> None:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE canvas_configs SET deleted_at = ? WHERE id = ?", (now, config_id)
        )
        conn.commit()

    def update_canvas_cookies(self, config_id: int, session_cookies: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE canvas_configs SET session_cookies = ?, status = 'active' WHERE id = ?",
            (session_cookies, config_id),
        )
        conn.commit()

    def update_canvas_status(self, config_id: int, status: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE canvas_configs SET status = ? WHERE id = ?", (status, config_id)
        )
        conn.commit()

    def update_canvas_last_sync(self, config_id: int, timestamp: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE canvas_configs SET last_sync = ? WHERE id = ?", (timestamp, config_id)
        )
        conn.commit()

    # --- Task CRUD ---

    def upsert_task(
        self,
        source: str,
        external_id: str,
        title: str,
        description: str | None = None,
        course: str | None = None,
        deadline: str | None = None,
        estimated_minutes: int | None = None,
        priority: int = 3,
        status: str = "pending",
        grade_weight: float | None = None,
        current_grade: str | None = None,
        ai_notes: str | None = None,
    ) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id FROM tasks WHERE source = ? AND external_id = ?",
            (source, external_id),
        )
        row = cursor.fetchone()
        if row:
            conn.execute(
                """UPDATE tasks SET title=?, description=?, course=?, deadline=?,
                   estimated_minutes=?, priority=?, status=?, grade_weight=?,
                   current_grade=?, ai_notes=?
                   WHERE id=?""",
                (title, description, course, deadline, estimated_minutes,
                 priority, status, grade_weight, current_grade, ai_notes, row[0]),
            )
            conn.commit()
            return row[0]
        cursor = conn.execute(
            """INSERT INTO tasks (source, external_id, title, description, course,
               deadline, estimated_minutes, priority, status, grade_weight,
               current_grade, ai_notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (source, external_id, title, description, course, deadline,
             estimated_minutes, priority, status, grade_weight, current_grade, ai_notes),
        )
        conn.commit()
        return cursor.lastrowid

    def get_tasks(
        self,
        source: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM tasks WHERE 1=1"
        params: list = []
        if source:
            query += " AND source = ?"
            params.append(source)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY deadline"
        cursor = conn.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.row_factory = None
        return rows

    def update_task_status(self, task_id: int, status: str) -> None:
        conn = self._get_conn()
        updates = "status = ?"
        params: list = [status]
        if status == "done":
            now = datetime.now(timezone.utc).isoformat()
            updates += ", completed_at = ?"
            params.append(now)
        params.append(task_id)
        conn.execute(f"UPDATE tasks SET {updates} WHERE id = ?", params)
        conn.commit()

    # --- Schedule Block CRUD ---

    def add_schedule_block(self, date, start_time, end_time, block_type, task_id=None, ai_reason=None, status="scheduled"):
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO schedule_blocks (task_id, date, start_time, end_time, block_type, status, ai_reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task_id, date, start_time, end_time, block_type, status, ai_reason),
        )
        conn.commit()
        return cursor.lastrowid

    def get_schedule_blocks(self, date):
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM schedule_blocks WHERE date = ? ORDER BY start_time", (date,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.row_factory = None
        return rows

    def update_block_status(self, block_id, status):
        conn = self._get_conn()
        conn.execute("UPDATE schedule_blocks SET status = ? WHERE id = ?", (status, block_id))
        conn.commit()

    def clear_schedule_blocks(self, date, preserve_completed=False):
        conn = self._get_conn()
        if preserve_completed:
            conn.execute("DELETE FROM schedule_blocks WHERE date = ? AND status != 'completed'", (date,))
        else:
            conn.execute("DELETE FROM schedule_blocks WHERE date = ?", (date,))
        conn.commit()

    # --- Reminder CRUD ---

    def add_reminder(
        self,
        remind_at: str,
        reminder_type: str,
        message: str,
        schedule_block_id: int | None = None,
        task_id: int | None = None,
        urgent: bool = False,
    ) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            """INSERT INTO reminders (schedule_block_id, task_id, remind_at,
               reminder_type, message, urgent)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (schedule_block_id, task_id, remind_at, reminder_type, message, int(urgent)),
        )
        conn.commit()
        return cursor.lastrowid

    def get_pending_reminders(self) -> list[dict]:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM reminders WHERE fired = 0 ORDER BY remind_at"
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.row_factory = None
        return rows

    def get_due_reminders(self, current_time: str) -> list[dict]:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM reminders WHERE fired = 0 AND remind_at <= ? ORDER BY remind_at",
            (current_time,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.row_factory = None
        return rows

    def mark_reminder_fired(self, reminder_id: int) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,)
        )
        conn.commit()

    def clear_reminders_for_date(self, date: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM reminders WHERE remind_at LIKE ?", (f"{date}%",)
        )
        conn.commit()

    # --- AI Context Cache ---

    def save_ai_cache(self, date, context_hash, schedule_json, tokens_used):
        conn = self._get_conn()
        conn.execute("INSERT INTO ai_context_cache (date, context_hash, schedule_json, tokens_used) VALUES (?, ?, ?, ?)", (date, context_hash, schedule_json, tokens_used))
        conn.commit()

    def get_ai_cache(self, date):
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM ai_context_cache WHERE date = ? ORDER BY created_at DESC LIMIT 1", (date,))
        row = cursor.fetchone()
        conn.row_factory = None
        return dict(row) if row else None
