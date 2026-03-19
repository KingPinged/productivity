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
    db.add_schedule_block(
        date="2026-03-20", start_time="09:00", end_time="10:30",
        block_type="study", ai_reason="Due tomorrow",
    )
    db.add_schedule_block(
        date="2026-03-20", start_time="10:30", end_time="10:45",
        block_type="rest",
    )
    db.close()

class TestScheduleRoutes:
    def test_get_schedule_returns_blocks(self, client, auth_headers, seeded_db):
        resp = client.get("/api/schedule/2026-03-20", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["date"] == "2026-03-20"
        assert len(data["blocks"]) == 2
        assert data["blocks"][0]["block_type"] == "study"

    def test_get_schedule_empty_date(self, client, auth_headers):
        resp = client.get("/api/schedule/2026-03-25", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["blocks"] == []

    def test_update_block_status(self, client, auth_headers, seeded_db):
        resp = client.get("/api/schedule/2026-03-20", headers=auth_headers)
        block_id = resp.json()["blocks"][0]["id"]
        resp = client.patch(
            f"/api/schedule/{block_id}",
            json={"status": "completed"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        resp = client.get("/api/schedule/2026-03-20", headers=auth_headers)
        block = [b for b in resp.json()["blocks"] if b["id"] == block_id][0]
        assert block["status"] == "completed"

    def test_schedule_requires_auth(self, client):
        assert client.get("/api/schedule/2026-03-20").status_code == 401
