import os
import tempfile
import pytest

os.environ.setdefault("PLANNER_PASSWORD", "testpass123")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-key")

from src.planner.db import PlannerDB
from fastapi.testclient import TestClient
from src.planner.server import create_app


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def db(db_path):
    database = PlannerDB(db_path)
    database.initialize()
    yield database
    database.close()


@pytest.fixture
def client(db_path):
    app = create_app(db_path=db_path)
    with TestClient(app) as c:
        yield c


def get_token(client):
    resp = client.post("/auth/login", json={"password": "testpass123"})
    return resp.json()["token"]


class TestPushSubscriptionDB:
    def test_add_subscription(self, db):
        sid = db.add_push_subscription("https://endpoint.example.com", "p256dh-key", "auth-key")
        assert sid > 0

    def test_list_subscriptions(self, db):
        db.add_push_subscription("https://endpoint1.com", "key1", "auth1")
        db.add_push_subscription("https://endpoint2.com", "key2", "auth2")
        subs = db.get_push_subscriptions()
        assert len(subs) == 2

    def test_duplicate_endpoint_updates(self, db):
        db.add_push_subscription("https://endpoint.com", "key1", "auth1")
        db.add_push_subscription("https://endpoint.com", "key2", "auth2")
        subs = db.get_push_subscriptions()
        assert len(subs) == 1
        assert subs[0]["p256dh"] == "key2"

    def test_remove_subscription(self, db):
        db.add_push_subscription("https://endpoint.com", "key", "auth")
        db.remove_push_subscription("https://endpoint.com")
        assert db.get_push_subscriptions() == []


class TestPushAPI:
    def test_get_vapid_key(self, client):
        token = get_token(client)
        resp = client.get("/api/push/vapid-key", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "public_key" in resp.json()

    def test_subscribe(self, client):
        token = get_token(client)
        resp = client.post("/api/push/subscribe", json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/test",
            "keys": {"p256dh": "test-key", "auth": "test-auth"},
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
