import os
import tempfile
from datetime import datetime, timezone

import pytest

from src.planner.db import PlannerDB


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


class TestAccountCRUD:
    def test_add_account(self, db):
        account_id = db.add_account("user@gmail.com", "google", "gmail.readonly calendar.readonly")
        assert account_id > 0

    def test_add_duplicate_account_returns_existing(self, db):
        id1 = db.add_account("user@gmail.com", "google", "gmail.readonly")
        id2 = db.add_account("user@gmail.com", "google", "gmail.readonly")
        assert id1 == id2

    def test_list_accounts(self, db):
        db.add_account("a@gmail.com", "google", "gmail.readonly")
        db.add_account("b@gmail.com", "google", "gmail.readonly")
        accounts = db.list_accounts()
        assert len(accounts) == 2
        assert accounts[0]["email"] == "a@gmail.com"
        assert accounts[1]["email"] == "b@gmail.com"

    def test_list_accounts_excludes_deleted(self, db):
        aid = db.add_account("a@gmail.com", "google", "gmail.readonly")
        db.soft_delete_account(aid)
        assert db.list_accounts() == []

    def test_soft_delete_account(self, db):
        aid = db.add_account("a@gmail.com", "google", "gmail.readonly")
        db.soft_delete_account(aid)
        accounts = db.list_accounts()
        assert len(accounts) == 0

    def test_get_account(self, db):
        aid = db.add_account("a@gmail.com", "google", "gmail.readonly")
        account = db.get_account(aid)
        assert account["email"] == "a@gmail.com"
        assert account["provider"] == "google"

    def test_update_last_sync(self, db):
        aid = db.add_account("a@gmail.com", "google", "gmail.readonly")
        now = datetime.now(timezone.utc).isoformat()
        db.update_account_last_sync(aid, now)
        account = db.get_account(aid)
        assert account["last_sync"] == now


class TestEventCRUD:
    def test_upsert_event(self, db):
        aid = db.add_account("a@gmail.com", "google", "gmail.readonly")
        event_id = db.upsert_event(
            account_id=aid,
            source="gcal",
            external_id="gcal:cal1:evt1",
            title="Team Meeting",
            start_time="2026-03-20T14:00:00Z",
            end_time="2026-03-20T15:00:00Z",
            event_type="meeting",
        )
        assert event_id > 0

    def test_upsert_event_dedup(self, db):
        aid = db.add_account("a@gmail.com", "google", "gmail.readonly")
        id1 = db.upsert_event(
            account_id=aid, source="gcal", external_id="gcal:cal1:evt1",
            title="Meeting v1", start_time="2026-03-20T14:00:00Z",
            end_time="2026-03-20T15:00:00Z",
        )
        id2 = db.upsert_event(
            account_id=aid, source="gcal", external_id="gcal:cal1:evt1",
            title="Meeting v2", start_time="2026-03-20T14:00:00Z",
            end_time="2026-03-20T15:00:00Z",
        )
        assert id1 == id2
        event = db.get_events(source="gcal")[0]
        assert event["title"] == "Meeting v2"

    def test_get_events_by_date_range(self, db):
        aid = db.add_account("a@gmail.com", "google", "gmail.readonly")
        db.upsert_event(
            account_id=aid, source="gcal", external_id="evt1",
            title="Event 1", start_time="2026-03-20T10:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )
        db.upsert_event(
            account_id=aid, source="gcal", external_id="evt2",
            title="Event 2", start_time="2026-03-25T10:00:00Z",
            end_time="2026-03-25T11:00:00Z",
        )
        events = db.get_events(start_after="2026-03-19", end_before="2026-03-21")
        assert len(events) == 1
        assert events[0]["title"] == "Event 1"

    def test_get_events_by_source(self, db):
        aid = db.add_account("a@gmail.com", "google", "gmail.readonly")
        db.upsert_event(
            account_id=aid, source="gcal", external_id="evt1",
            title="Cal Event", start_time="2026-03-20T10:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )
        db.upsert_event(
            account_id=aid, source="gmail", external_id="mail1",
            title="Email Event", start_time="2026-03-20T10:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )
        events = db.get_events(source="gcal")
        assert len(events) == 1
        assert events[0]["title"] == "Cal Event"

    def test_delete_events_for_account(self, db):
        aid = db.add_account("a@gmail.com", "google", "gmail.readonly")
        db.upsert_event(
            account_id=aid, source="gcal", external_id="evt1",
            title="Event", start_time="2026-03-20T10:00:00Z",
            end_time="2026-03-20T11:00:00Z",
        )
        db.delete_events_for_account(aid)
        assert db.get_events() == []
