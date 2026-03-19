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


class TestCanvasConfigCRUD:
    def test_add_canvas_config(self, db):
        cid = db.add_canvas_config("https://canvas.university.edu", "encrypted-cookies")
        assert cid > 0

    def test_get_canvas_config(self, db):
        cid = db.add_canvas_config("https://canvas.university.edu", "encrypted-cookies")
        config = db.get_canvas_config(cid)
        assert config["canvas_url"] == "https://canvas.university.edu"
        assert config["session_cookies"] == "encrypted-cookies"
        assert config["status"] == "active"

    def test_list_canvas_configs(self, db):
        db.add_canvas_config("https://canvas1.edu", "cookies1")
        db.add_canvas_config("https://canvas2.edu", "cookies2")
        configs = db.list_canvas_configs()
        assert len(configs) == 2

    def test_list_excludes_deleted(self, db):
        cid = db.add_canvas_config("https://canvas.edu", "cookies")
        db.soft_delete_canvas_config(cid)
        assert db.list_canvas_configs() == []

    def test_update_canvas_cookies(self, db):
        cid = db.add_canvas_config("https://canvas.edu", "old-cookies")
        db.update_canvas_cookies(cid, "new-cookies")
        config = db.get_canvas_config(cid)
        assert config["session_cookies"] == "new-cookies"

    def test_update_canvas_status(self, db):
        cid = db.add_canvas_config("https://canvas.edu", "cookies")
        db.update_canvas_status(cid, "expired")
        config = db.get_canvas_config(cid)
        assert config["status"] == "expired"

    def test_update_canvas_last_sync(self, db):
        cid = db.add_canvas_config("https://canvas.edu", "cookies")
        db.update_canvas_last_sync(cid, "2026-03-19T12:00:00Z")
        config = db.get_canvas_config(cid)
        assert config["last_sync"] == "2026-03-19T12:00:00Z"


class TestTaskCRUD:
    def test_upsert_task(self, db):
        tid = db.upsert_task(
            source="canvas", external_id="canvas:CS101:hw1",
            title="Homework 1", course="CS 101",
            deadline="2026-03-25T23:59:00Z", estimated_minutes=60,
        )
        assert tid > 0

    def test_upsert_task_dedup(self, db):
        id1 = db.upsert_task(source="canvas", external_id="canvas:CS101:hw1",
            title="HW1 v1", course="CS 101", deadline="2026-03-25T23:59:00Z")
        id2 = db.upsert_task(source="canvas", external_id="canvas:CS101:hw1",
            title="HW1 v2", course="CS 101", deadline="2026-03-26T23:59:00Z")
        assert id1 == id2
        tasks = db.get_tasks(source="canvas")
        assert len(tasks) == 1
        assert tasks[0]["title"] == "HW1 v2"

    def test_get_tasks_by_status(self, db):
        db.upsert_task(source="canvas", external_id="t1", title="Task 1", status="pending")
        db.upsert_task(source="canvas", external_id="t2", title="Task 2", status="done")
        pending = db.get_tasks(status="pending")
        assert len(pending) == 1
        assert pending[0]["title"] == "Task 1"

    def test_get_tasks_by_source(self, db):
        db.upsert_task(source="canvas", external_id="t1", title="Canvas Task")
        db.upsert_task(source="manual", external_id="t2", title="Manual Task")
        canvas_tasks = db.get_tasks(source="canvas")
        assert len(canvas_tasks) == 1

    def test_update_task_status(self, db):
        tid = db.upsert_task(source="canvas", external_id="t1", title="Task")
        db.update_task_status(tid, "done")
        task = db.get_tasks(source="canvas")[0]
        assert task["status"] == "done"

    def test_update_task_grade_info(self, db):
        tid = db.upsert_task(source="canvas", external_id="t1", title="Task",
            course="CS 101", grade_weight=0.15, current_grade="B-")
        tasks = db.get_tasks(source="canvas")
        assert tasks[0]["grade_weight"] == 0.15
        assert tasks[0]["current_grade"] == "B-"
