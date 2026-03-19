import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.planner.server import create_app

FAKE_CLIENT_CONFIG = {
    "web": {
        "client_id": "fake.apps.googleusercontent.com",
        "client_secret": "fake-secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8321/auth/callback"],
    }
}

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
    app = create_app(
        db_path=db_path,
        auth_token=token,
        google_client_config=FAKE_CLIENT_CONFIG,
    )
    with TestClient(app) as c:
        yield c

@pytest.fixture
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


class TestAuthRoutes:
    def test_get_auth_google_returns_redirect_url(self, client, auth_headers):
        resp = client.get("/auth/google", headers=auth_headers, follow_redirects=False)
        assert resp.status_code == 200
        data = resp.json()
        assert "auth_url" in data
        assert "accounts.google.com" in data["auth_url"]

    def test_list_accounts_empty(self, client, auth_headers):
        resp = client.get("/auth/accounts", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_accounts_after_add(self, client, auth_headers, db_path):
        from src.planner.db import PlannerDB
        db = PlannerDB(db_path)
        db.add_account("test@gmail.com", "google", "gmail.readonly")
        db.close()

        resp = client.get("/auth/accounts", headers=auth_headers)
        assert resp.status_code == 200
        accounts = resp.json()
        assert len(accounts) == 1
        assert accounts[0]["email"] == "test@gmail.com"

    def test_delete_account(self, client, auth_headers, db_path):
        from src.planner.db import PlannerDB
        db = PlannerDB(db_path)
        aid = db.add_account("test@gmail.com", "google", "gmail.readonly")
        db.close()

        with patch("src.planner.api.auth.auth_manager") as mock_auth:
            resp = client.delete(f"/auth/accounts/{aid}", headers=auth_headers)
            assert resp.status_code == 200

        resp = client.get("/auth/accounts", headers=auth_headers)
        assert resp.json() == []

    def test_auth_routes_require_auth(self, client):
        assert client.get("/auth/accounts").status_code == 401
        assert client.get("/auth/google").status_code == 401
