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

class TestScheduleBlockCRUD:
    def test_add_schedule_block(self, db):
        bid = db.add_schedule_block(
            date="2026-03-20", start_time="09:00", end_time="10:30",
            block_type="study", ai_reason="Due tomorrow",
        )
        assert bid > 0

    def test_add_block_with_task(self, db):
        tid = db.upsert_task(source="canvas", external_id="t1", title="HW1")
        bid = db.add_schedule_block(
            date="2026-03-20", start_time="09:00", end_time="10:30",
            block_type="study", task_id=tid,
        )
        blocks = db.get_schedule_blocks("2026-03-20")
        assert len(blocks) == 1
        assert blocks[0]["task_id"] == tid

    def test_get_schedule_blocks_by_date(self, db):
        db.add_schedule_block(date="2026-03-20", start_time="09:00", end_time="10:00", block_type="study")
        db.add_schedule_block(date="2026-03-20", start_time="10:15", end_time="10:30", block_type="rest")
        db.add_schedule_block(date="2026-03-21", start_time="09:00", end_time="10:00", block_type="study")
        blocks = db.get_schedule_blocks("2026-03-20")
        assert len(blocks) == 2

    def test_update_block_status(self, db):
        bid = db.add_schedule_block(
            date="2026-03-20", start_time="09:00", end_time="10:00", block_type="study",
        )
        db.update_block_status(bid, "completed")
        blocks = db.get_schedule_blocks("2026-03-20")
        assert blocks[0]["status"] == "completed"

    def test_clear_schedule_for_date(self, db):
        db.add_schedule_block(date="2026-03-20", start_time="09:00", end_time="10:00", block_type="study")
        db.add_schedule_block(date="2026-03-20", start_time="10:00", end_time="10:15", block_type="rest")
        db.clear_schedule_blocks("2026-03-20")
        assert db.get_schedule_blocks("2026-03-20") == []

    def test_clear_preserves_completed_blocks(self, db):
        bid1 = db.add_schedule_block(date="2026-03-20", start_time="09:00", end_time="10:00", block_type="study")
        bid2 = db.add_schedule_block(date="2026-03-20", start_time="10:00", end_time="11:00", block_type="study")
        db.update_block_status(bid1, "completed")
        db.clear_schedule_blocks("2026-03-20", preserve_completed=True)
        blocks = db.get_schedule_blocks("2026-03-20")
        assert len(blocks) == 1
        assert blocks[0]["status"] == "completed"

class TestAIContextCache:
    def test_save_and_get_cache(self, db):
        db.save_ai_cache("2026-03-20", "hash123", '{"schedule":[]}', 5000)
        cache = db.get_ai_cache("2026-03-20")
        assert cache is not None
        assert cache["context_hash"] == "hash123"
        assert cache["tokens_used"] == 5000

    def test_get_cache_missing(self, db):
        assert db.get_ai_cache("2026-03-20") is None
