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
    db.initialize()
    db.add_reminder(
        remind_at="2026-03-20T08:00:00Z", reminder_type="task_start",
        message="Start studying",
    )
    db.add_reminder(
        remind_at="2026-03-20T10:00:00Z", reminder_type="break",
        message="Take a break",
    )
    db.close()

class TestReminderRoutes:
    def test_get_pending_reminders(self, client, auth_headers, seeded_db):
        resp = client.get("/api/reminders", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_dismiss_reminder(self, client, auth_headers, seeded_db):
        resp = client.get("/api/reminders", headers=auth_headers)
        rid = resp.json()[0]["id"]
        resp = client.patch(
            f"/api/reminders/{rid}",
            json={"action": "dismiss"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        resp = client.get("/api/reminders", headers=auth_headers)
        assert len(resp.json()) == 1

    def test_reminders_require_auth(self, client):
        assert client.get("/api/reminders").status_code == 401
