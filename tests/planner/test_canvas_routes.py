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

class TestCanvasRoutes:
    def test_list_canvas_configs_empty(self, client, auth_headers):
        resp = client.get("/canvas/configs", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_canvas_configs_after_add(self, client, auth_headers, db_path):
        db = PlannerDB(db_path)
        db.add_canvas_config("https://canvas.edu", "cookies")
        db.close()
        resp = client.get("/canvas/configs", headers=auth_headers)
        configs = resp.json()
        assert len(configs) == 1
        assert configs[0]["canvas_url"] == "https://canvas.edu"
        assert "session_cookies" not in configs[0]

    def test_delete_canvas_config(self, client, auth_headers, db_path):
        db = PlannerDB(db_path)
        cid = db.add_canvas_config("https://canvas.edu", "cookies")
        db.close()
        resp = client.delete(f"/canvas/configs/{cid}", headers=auth_headers)
        assert resp.status_code == 200
        resp = client.get("/canvas/configs", headers=auth_headers)
        assert resp.json() == []

    def test_canvas_routes_require_auth(self, client):
        assert client.get("/canvas/configs").status_code == 401
