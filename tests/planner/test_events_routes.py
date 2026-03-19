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
    aid = db.add_account("user@gmail.com", "google", "gmail.readonly")
    db.upsert_event(
        account_id=aid, source="gcal", external_id="evt1",
        title="Meeting", start_time="2026-03-20T14:00:00Z",
        end_time="2026-03-20T15:00:00Z", event_type="meeting",
    )
    db.upsert_event(
        account_id=aid, source="gmail", external_id="mail1",
        title="Email Action", start_time="2026-03-21T10:00:00Z",
        end_time="2026-03-21T10:30:00Z", event_type="email",
    )
    db.close()

class TestEventsRoute:
    def test_get_all_events(self, client, auth_headers, seeded_db):
        resp = client.get("/api/events", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_filter_events_by_source(self, client, auth_headers, seeded_db):
        resp = client.get("/api/events?source=gcal", headers=auth_headers)
        events = resp.json()
        assert len(events) == 1
        assert events[0]["title"] == "Meeting"

    def test_filter_events_by_date(self, client, auth_headers, seeded_db):
        resp = client.get(
            "/api/events?start_after=2026-03-20&end_before=2026-03-21",
            headers=auth_headers,
        )
        events = resp.json()
        assert len(events) == 1
        assert events[0]["title"] == "Meeting"

    def test_events_require_auth(self, client):
        assert client.get("/api/events").status_code == 401
