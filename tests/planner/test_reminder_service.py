import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.planner.db import PlannerDB
from src.planner.reminders.service import ReminderService


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
def mock_notifier():
    return MagicMock()


class TestReminderService:
    def test_generate_block_reminders(self, db, mock_notifier):
        db.add_schedule_block(
            date="2026-03-20", start_time="09:00", end_time="10:30",
            block_type="study", ai_reason="Calculus due tomorrow",
        )
        db.add_schedule_block(
            date="2026-03-20", start_time="10:30", end_time="10:45",
            block_type="rest",
        )

        service = ReminderService(db, mock_notifier)
        service.generate_reminders_for_date("2026-03-20")

        reminders = db.get_pending_reminders()
        # Should have: task_start for study block + break for rest block
        types = {r["reminder_type"] for r in reminders}
        assert "task_start" in types
        assert "break" in types

    def test_generate_deadline_reminders(self, db, mock_notifier):
        db.upsert_task(
            source="canvas", external_id="t1", title="Calculus PS4",
            deadline="2026-03-21T23:59:00Z",
        )

        service = ReminderService(db, mock_notifier)
        service.generate_deadline_reminders()

        reminders = db.get_pending_reminders()
        deadline_reminders = [r for r in reminders if r["reminder_type"] == "deadline"]
        assert len(deadline_reminders) >= 1

    def test_fire_due_reminders(self, db, mock_notifier):
        db.add_reminder(
            remind_at="2026-03-20T08:00:00Z",
            reminder_type="task_start",
            message="Time to start studying",
        )

        service = ReminderService(db, mock_notifier)
        service.check_and_fire("2026-03-20T08:01:00Z")

        mock_notifier.send.assert_called_once()
        assert db.get_pending_reminders() == []

    def test_quiet_hours_suppress_non_urgent(self, db, mock_notifier):
        db.set_preference("quiet_hours_start", "23:00")
        db.set_preference("quiet_hours_end", "07:00")

        db.add_reminder(
            remind_at="2026-03-20T02:00:00Z",
            reminder_type="task_start",
            message="Non-urgent during quiet hours",
        )

        service = ReminderService(db, mock_notifier)
        service.check_and_fire("2026-03-20T02:01:00Z")

        mock_notifier.send.assert_not_called()

    def test_urgent_fires_during_quiet_hours(self, db, mock_notifier):
        db.set_preference("quiet_hours_start", "23:00")
        db.set_preference("quiet_hours_end", "07:00")

        db.add_reminder(
            remind_at="2026-03-20T02:00:00Z",
            reminder_type="deadline",
            message="Assignment due in 3 hours!",
            urgent=True,
        )

        service = ReminderService(db, mock_notifier)
        service.check_and_fire("2026-03-20T02:01:00Z")

        mock_notifier.send.assert_called_once()

    def test_does_not_double_fire(self, db, mock_notifier):
        db.add_reminder(
            remind_at="2026-03-20T08:00:00Z",
            reminder_type="event",
            message="Meeting",
        )

        service = ReminderService(db, mock_notifier)
        service.check_and_fire("2026-03-20T08:01:00Z")
        service.check_and_fire("2026-03-20T08:02:00Z")

        assert mock_notifier.send.call_count == 1
