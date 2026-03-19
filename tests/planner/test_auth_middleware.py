import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.planner.api.auth_middleware import create_token_dependency


@pytest.fixture
def app_with_auth():
    app = FastAPI()
    valid_token = "test-secret-token-abc123"
    require_token = create_token_dependency(valid_token)

    @app.get("/protected")
    def protected(token: str = require_token):
        return {"status": "ok"}

    return app, valid_token


@pytest.fixture
def client(app_with_auth):
    app, _ = app_with_auth
    return TestClient(app)


@pytest.fixture
def token(app_with_auth):
    _, t = app_with_auth
    return t


class TestAuthMiddleware:
    def test_valid_token_allows_access(self, client, token):
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_missing_header_returns_401(self, client):
        resp = client.get("/protected")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client):
        resp = client.get("/protected", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    def test_malformed_header_returns_401(self, client):
        resp = client.get("/protected", headers={"Authorization": "NotBearer token"})
        assert resp.status_code == 401
