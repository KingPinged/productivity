import os
import sqlite3
import tempfile

import pytest

from src.planner.db import PlannerDB


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def db(db_path):
    database = PlannerDB(db_path)
    database.initialize()
    yield database
    database.close()


class TestSchemaCreation:
    def test_creates_all_tables(self, db, db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        expected = {
            "accounts",
            "canvas_configs",
            "events",
            "tasks",
            "schedule_blocks",
            "reminders",
            "preferences",
            "ai_context_cache",
            "schema_version",
        }
        assert expected.issubset(tables)

    def test_initialize_is_idempotent(self, db):
        db.initialize()
        db.initialize()

    def test_schema_version_is_set(self, db, db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT version FROM schema_version")
        version = cursor.fetchone()[0]
        conn.close()
        assert version == 1


class TestPreferencesCRUD:
    def test_set_and_get_preference(self, db):
        db.set_preference("wake_time", "07:00")
        assert db.get_preference("wake_time") == "07:00"

    def test_get_missing_preference_returns_none(self, db):
        assert db.get_preference("nonexistent") is None

    def test_get_preference_with_default(self, db):
        assert db.get_preference("missing", "fallback") == "fallback"

    def test_update_existing_preference(self, db):
        db.set_preference("wake_time", "07:00")
        db.set_preference("wake_time", "08:00")
        assert db.get_preference("wake_time") == "08:00"

    def test_get_all_preferences(self, db):
        db.set_preference("wake_time", "07:00")
        db.set_preference("sleep_time", "23:00")
        prefs = db.get_all_preferences()
        assert prefs == {"wake_time": "07:00", "sleep_time": "23:00"}

    def test_get_all_preferences_empty(self, db):
        assert db.get_all_preferences() == {}
