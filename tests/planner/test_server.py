import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from src.planner.server import create_app


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def token():
    return "test-token-xyz"


@pytest.fixture
def client(db_path, token):
    app = create_app(db_path=db_path, auth_token=token)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_health_requires_no_auth(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200


class TestPreferencesAPI:
    def test_get_preferences_empty(self, client, auth_headers):
        resp = client.get("/api/preferences", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_set_and_get_preferences(self, client, auth_headers):
        resp = client.patch(
            "/api/preferences",
            json={"wake_time": "07:00", "sleep_time": "23:00"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        resp = client.get("/api/preferences", headers=auth_headers)
        data = resp.json()
        assert data["wake_time"] == "07:00"
        assert data["sleep_time"] == "23:00"

    def test_update_existing_preference(self, client, auth_headers):
        client.patch(
            "/api/preferences",
            json={"wake_time": "07:00"},
            headers=auth_headers,
        )
        client.patch(
            "/api/preferences",
            json={"wake_time": "08:30"},
            headers=auth_headers,
        )
        resp = client.get("/api/preferences", headers=auth_headers)
        assert resp.json()["wake_time"] == "08:30"

    def test_preferences_require_auth(self, client):
        resp = client.get("/api/preferences")
        assert resp.status_code == 401


class TestScheduleStub:
    def test_get_schedule_returns_empty(self, client, auth_headers):
        resp = client.get("/api/schedule/2026-03-19", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["date"] == "2026-03-19"
        assert data["blocks"] == []

    def test_schedule_requires_auth(self, client):
        resp = client.get("/api/schedule/2026-03-19")
        assert resp.status_code == 401
