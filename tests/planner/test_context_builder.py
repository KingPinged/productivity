import os
import tempfile
from datetime import datetime, timezone
import pytest
from src.planner.db import PlannerDB
from src.planner.ai.context_builder import ContextBuilder


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = PlannerDB(path)
    database.initialize()
    yield database
    database.close()
    os.unlink(path)


@pytest.fixture
def seeded_db(db):
    db.set_preference("wake_time", "07:00")
    db.set_preference("sleep_time", "23:00")
    db.set_preference("max_work_hours", "8")
    db.set_preference("break_frequency", "90")
    aid = db.add_account("user@gmail.com", "google", "gmail.readonly")
    db.upsert_event(
        account_id=aid, source="gcal", external_id="evt1",
        title="Team Meeting", start_time="2026-03-20T14:00:00Z",
        end_time="2026-03-20T15:00:00Z", event_type="meeting",
    )
    db.upsert_task(
        source="canvas", external_id="t1", title="Calculus PS4",
        course="MATH 201", deadline="2026-03-21T23:59:00Z",
        estimated_minutes=90, current_grade="B-",
    )
    db.upsert_task(
        source="canvas", external_id="t2", title="CS Lab Report",
        course="CS 301", deadline="2026-03-25T23:59:00Z",
        estimated_minutes=120, current_grade="A",
    )
    db.add_schedule_block(
        date="2026-03-20", start_time="08:00", end_time="09:00",
        block_type="study", status="completed",
    )
    return db


class TestContextBuilder:
    def test_build_context_returns_dict(self, seeded_db):
        builder = ContextBuilder(seeded_db)
        ctx = builder.build("2026-03-20")
        assert isinstance(ctx, dict)
        assert "date" in ctx
        assert "events" in ctx
        assert "tasks" in ctx
        assert "preferences" in ctx
        assert "completed_today" in ctx

    def test_context_includes_events(self, seeded_db):
        builder = ContextBuilder(seeded_db)
        ctx = builder.build("2026-03-20")
        assert len(ctx["events"]) >= 1
        assert ctx["events"][0]["title"] == "Team Meeting"

    def test_context_includes_pending_tasks(self, seeded_db):
        builder = ContextBuilder(seeded_db)
        ctx = builder.build("2026-03-20")
        assert len(ctx["tasks"]) == 2
        assert any(t["title"] == "Calculus PS4" for t in ctx["tasks"])

    def test_context_includes_preferences(self, seeded_db):
        builder = ContextBuilder(seeded_db)
        ctx = builder.build("2026-03-20")
        assert ctx["preferences"]["wake_time"] == "07:00"
        assert ctx["preferences"]["sleep_time"] == "23:00"

    def test_context_includes_completed_blocks(self, seeded_db):
        builder = ContextBuilder(seeded_db)
        ctx = builder.build("2026-03-20")
        assert len(ctx["completed_today"]) == 1

    def test_context_hash_changes_with_data(self, seeded_db):
        builder = ContextBuilder(seeded_db)
        hash1 = builder.compute_hash(builder.build("2026-03-20"))
        seeded_db.upsert_task(source="manual", external_id="t3", title="New Task")
        hash2 = builder.compute_hash(builder.build("2026-03-20"))
        assert hash1 != hash2

    def test_context_hash_stable_for_same_data(self, seeded_db):
        builder = ContextBuilder(seeded_db)
        ctx = builder.build("2026-03-20")
        hash1 = builder.compute_hash(ctx)
        hash2 = builder.compute_hash(ctx)
        assert hash1 == hash2
