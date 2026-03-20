import os
import tempfile
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("PLANNER_PASSWORD", "testpass123")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-key")

from src.planner.server import create_app


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def client(db_path):
    app = create_app(db_path=db_path)
    with TestClient(app) as c:
        yield c


def login(client):
    resp = client.post("/auth/login", json={"password": "testpass123"})
    return resp.json().get("token")


class TestJWTAuth:
    def test_login_with_correct_password(self, client):
        resp = client.post("/auth/login", json={"password": "testpass123"})
        assert resp.status_code == 200
        assert "token" in resp.json()

    def test_login_with_wrong_password(self, client):
        resp = client.post("/auth/login", json={"password": "wrong"})
        assert resp.status_code == 401

    def test_jwt_token_grants_access(self, client):
        token = login(client)
        resp = client.get("/api/preferences", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_no_token_returns_401(self, client):
        resp = client.get("/api/preferences")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client):
        resp = client.get("/api/preferences", headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 401

    def test_health_requires_no_auth(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
