import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from src.planner.db import PlannerDB
from src.planner.server import create_app

@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)

@pytest.fixture
def token():
    return "test-token"

@pytest.fixture
def client(db_path, token):
    app = create_app(db_path=db_path, auth_token=token)
    with TestClient(app) as c:
        yield c

@pytest.fixture
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def seeded_db(db_path):
    db = PlannerDB(db_path)
    db.upsert_task(source="canvas", external_id="t1", title="HW1", course="CS 101", deadline="2026-03-25T23:59:00Z")
    db.upsert_task(source="manual", external_id="t2", title="Buy groceries", status="pending")
    db.close()

class TestTaskRoutes:
    def test_list_tasks(self, client, auth_headers, seeded_db):
        resp = client.get("/api/tasks", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_filter_tasks_by_source(self, client, auth_headers, seeded_db):
        resp = client.get("/api/tasks?source=canvas", headers=auth_headers)
        tasks = resp.json()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "HW1"

    def test_filter_tasks_by_status(self, client, auth_headers, seeded_db):
        resp = client.get("/api/tasks?status=pending", headers=auth_headers)
        assert len(resp.json()) == 2

    def test_create_manual_task(self, client, auth_headers):
        resp = client.post(
            "/api/tasks",
            json={"title": "Study for exam", "deadline": "2026-03-30T14:00:00Z"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["task_id"] > 0
        resp = client.get("/api/tasks", headers=auth_headers)
        assert len(resp.json()) == 1

    def test_update_task_status(self, client, auth_headers, seeded_db):
        resp = client.get("/api/tasks", headers=auth_headers)
        task_id = resp.json()[0]["id"]
        resp = client.patch(f"/api/tasks/{task_id}", json={"status": "done"}, headers=auth_headers)
        assert resp.status_code == 200

    def test_delete_task(self, client, auth_headers, seeded_db):
        resp = client.get("/api/tasks", headers=auth_headers)
        task_id = resp.json()[0]["id"]
        resp = client.delete(f"/api/tasks/{task_id}", headers=auth_headers)
        assert resp.status_code == 200

    def test_tasks_require_auth(self, client):
        assert client.get("/api/tasks").status_code == 401
