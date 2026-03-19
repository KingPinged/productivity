import os
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

class TestReminderCRUD:
    def test_add_reminder(self, db):
        rid = db.add_reminder(
            remind_at="2026-03-20T08:30:00Z",
            reminder_type="task_start",
            message="Time to start: Calculus PS4",
        )
        assert rid > 0

    def test_add_reminder_with_block(self, db):
        bid = db.add_schedule_block(
            date="2026-03-20", start_time="09:00", end_time="10:00", block_type="study",
        )
        rid = db.add_reminder(
            remind_at="2026-03-20T09:00:00Z",
            reminder_type="task_start",
            message="Time to study",
            schedule_block_id=bid,
        )
        reminders = db.get_pending_reminders()
        assert len(reminders) == 1
        assert reminders[0]["schedule_block_id"] == bid

    def test_get_pending_reminders(self, db):
        db.add_reminder(
            remind_at="2026-03-20T08:00:00Z", reminder_type="task_start",
            message="Task 1",
        )
        db.add_reminder(
            remind_at="2026-03-20T09:00:00Z", reminder_type="break",
            message="Take a break",
        )
        reminders = db.get_pending_reminders()
        assert len(reminders) == 2

    def test_get_pending_excludes_fired(self, db):
        rid = db.add_reminder(
            remind_at="2026-03-20T08:00:00Z", reminder_type="task_start",
            message="Task 1",
        )
        db.mark_reminder_fired(rid)
        assert db.get_pending_reminders() == []

    def test_mark_reminder_fired(self, db):
        rid = db.add_reminder(
            remind_at="2026-03-20T08:00:00Z", reminder_type="event",
            message="Meeting soon",
        )
        db.mark_reminder_fired(rid)
        reminders = db.get_pending_reminders()
        assert len(reminders) == 0

    def test_get_due_reminders(self, db):
        db.add_reminder(
            remind_at="2026-03-20T08:00:00Z", reminder_type="task_start",
            message="Past reminder",
        )
        db.add_reminder(
            remind_at="2099-12-31T23:59:00Z", reminder_type="event",
            message="Future reminder",
        )
        due = db.get_due_reminders("2026-03-20T10:00:00Z")
        assert len(due) == 1
        assert due[0]["message"] == "Past reminder"

    def test_dismiss_reminder(self, db):
        rid = db.add_reminder(
            remind_at="2026-03-20T08:00:00Z", reminder_type="event",
            message="Meeting",
        )
        db.mark_reminder_fired(rid)
        assert len(db.get_pending_reminders()) == 0

    def test_clear_reminders_for_date(self, db):
        db.add_reminder(
            remind_at="2026-03-20T08:00:00Z", reminder_type="task_start",
            message="Today's reminder",
        )
        db.add_reminder(
            remind_at="2026-03-21T08:00:00Z", reminder_type="task_start",
            message="Tomorrow's reminder",
        )
        db.clear_reminders_for_date("2026-03-20")
        reminders = db.get_pending_reminders()
        assert len(reminders) == 1
        assert reminders[0]["message"] == "Tomorrow's reminder"
