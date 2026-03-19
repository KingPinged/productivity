import json
import os
import tempfile
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from src.planner.db import PlannerDB
from src.planner.ai.scheduler import AIScheduler


VALID_RESPONSE = json.dumps({
    "schedule": [
        {"start": "09:00", "end": "10:30", "task": "Calculus PS4", "type": "study", "priority": "high", "reason": "Due tomorrow"},
        {"start": "10:30", "end": "10:45", "task": "Break", "type": "rest", "priority": "low", "reason": "Scheduled break"},
        {"start": "10:45", "end": "12:00", "task": "CS Lab Report", "type": "study", "priority": "medium", "reason": "Due in 5 days"},
    ],
    "tasks_today": ["Calculus PS4", "CS Lab Report"],
    "tasks_later": ["History essay"],
    "reminders": [{"time": "13:30", "message": "Team meeting in 30 min", "urgent": True}],
})

OVERLAPPING_RESPONSE = json.dumps({
    "schedule": [
        {"start": "09:00", "end": "10:30", "task": "Task A", "type": "study", "priority": "high", "reason": "test"},
        {"start": "10:00", "end": "11:00", "task": "Task B", "type": "study", "priority": "medium", "reason": "overlaps"},
    ],
    "tasks_today": [], "tasks_later": [], "reminders": [],
})


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = PlannerDB(path)
    database.initialize()
    database.set_preference("wake_time", "07:00")
    database.set_preference("sleep_time", "23:00")
    yield database
    database.close()
    os.unlink(path)


@pytest.fixture
def mock_client():
    client = MagicMock()
    return client


class TestAIScheduler:
    def test_parse_valid_response(self, db):
        scheduler = AIScheduler(db, api_key="fake")
        result = scheduler.parse_response(VALID_RESPONSE)
        assert len(result["schedule"]) == 3
        assert result["schedule"][0]["task"] == "Calculus PS4"
        assert result["tasks_today"] == ["Calculus PS4", "CS Lab Report"]

    def test_parse_invalid_json_returns_none(self, db):
        scheduler = AIScheduler(db, api_key="fake")
        result = scheduler.parse_response("not json at all")
        assert result is None

    def test_parse_missing_schedule_key_returns_none(self, db):
        scheduler = AIScheduler(db, api_key="fake")
        result = scheduler.parse_response('{"tasks_today": []}')
        assert result is None

    def test_detect_overlapping_blocks(self, db):
        scheduler = AIScheduler(db, api_key="fake")
        result = scheduler.parse_response(OVERLAPPING_RESPONSE)
        assert result is not None
        assert scheduler.has_overlaps(result["schedule"])

    def test_no_overlaps_in_valid_schedule(self, db):
        scheduler = AIScheduler(db, api_key="fake")
        result = scheduler.parse_response(VALID_RESPONSE)
        assert not scheduler.has_overlaps(result["schedule"])

    def test_store_schedule_blocks(self, db):
        scheduler = AIScheduler(db, api_key="fake")
        result = scheduler.parse_response(VALID_RESPONSE)
        scheduler.store_schedule("2026-03-20", result)
        blocks = db.get_schedule_blocks("2026-03-20")
        assert len(blocks) == 3
        assert blocks[0]["block_type"] == "study"
        assert blocks[0]["start_time"] == "09:00"

    def test_store_clears_existing_non_completed(self, db):
        db.add_schedule_block(date="2026-03-20", start_time="08:00", end_time="09:00", block_type="study")
        completed_id = db.add_schedule_block(
            date="2026-03-20", start_time="07:00", end_time="08:00",
            block_type="study", status="completed",
        )
        scheduler = AIScheduler(db, api_key="fake")
        result = scheduler.parse_response(VALID_RESPONSE)
        scheduler.store_schedule("2026-03-20", result)
        blocks = db.get_schedule_blocks("2026-03-20")
        # 1 completed (preserved) + 3 new
        assert len(blocks) == 4

    def test_generate_calls_claude(self, db, mock_client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=VALID_RESPONSE)]
        mock_response.usage.input_tokens = 1000
        mock_response.usage.output_tokens = 500
        mock_client.messages.create.return_value = mock_response

        scheduler = AIScheduler(db, api_key="fake")
        scheduler._client = mock_client
        result = scheduler.generate("2026-03-20")
        assert result is not None
        assert len(result["schedule"]) == 3
        mock_client.messages.create.assert_called_once()
