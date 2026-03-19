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
    return "test-token"

@pytest.fixture
def client(db_path, token):
    app = create_app(db_path=db_path, auth_token=token)
    with TestClient(app) as c:
        yield c

@pytest.fixture
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}

class TestSyncRoutes:
    def test_get_sync_status(self, client, auth_headers):
        resp = client.get("/sync/status", headers=auth_headers)
        assert resp.status_code == 200
        assert "accounts" in resp.json()

    def test_trigger_sync(self, client, auth_headers):
        resp = client.post("/sync/trigger", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "triggered"

    def test_sync_routes_require_auth(self, client):
        assert client.get("/sync/status").status_code == 401
        assert client.post("/sync/trigger").status_code == 401
