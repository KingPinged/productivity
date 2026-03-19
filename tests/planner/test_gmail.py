import base64
import os
import tempfile
from unittest.mock import MagicMock

import pytest

from src.planner.db import PlannerDB
from src.planner.ingestion.gmail import GmailSyncer


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = PlannerDB(path)
    database.initialize()
    yield database
    database.close()
    os.unlink(path)


def _make_message(msg_id: str, subject: str, body: str, label_ids: list[str] | None = None):
    encoded_body = base64.urlsafe_b64encode(body.encode()).decode()
    return {
        "id": msg_id,
        "labelIds": label_ids or ["INBOX"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": "sender@example.com"},
                {"name": "Date", "value": "Thu, 19 Mar 2026 10:00:00 -0500"},
            ],
            "body": {"data": encoded_body},
            "parts": [],
        },
        "snippet": body[:100],
    }


@pytest.fixture
def mock_service():
    service = MagicMock()
    return service


class TestGmailSyncer:
    def test_fetch_recent_messages(self, db, mock_service):
        aid = db.add_account("user@gmail.com", "google", "gmail.readonly")
        mock_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1"}, {"id": "msg2"}],
        }
        mock_service.users().messages().get().execute.side_effect = [
            _make_message("msg1", "HW Due Friday", "Complete problem set 5 by Friday"),
            _make_message("msg2", "Meeting Tomorrow", "Team sync at 2pm"),
        ]

        syncer = GmailSyncer(db)
        messages = syncer.fetch_recent_messages(mock_service, max_results=10)
        assert len(messages) == 2

    def test_extract_email_metadata(self, db):
        syncer = GmailSyncer(db)
        msg = _make_message("msg1", "HW Due Friday", "Complete problem set 5")
        meta = syncer.extract_metadata(msg)
        assert meta["subject"] == "HW Due Friday"
        assert meta["from"] == "sender@example.com"
        assert meta["message_id"] == "msg1"

    def test_store_email_as_event(self, db):
        aid = db.add_account("user@gmail.com", "google", "gmail.readonly")
        syncer = GmailSyncer(db)
        syncer.store_email_event(
            account_id=aid,
            message_id="msg1",
            subject="Team Meeting",
            date_str="2026-03-20T14:00:00Z",
            snippet="Team sync at 2pm tomorrow",
        )
        events = db.get_events(source="gmail")
        assert len(events) == 1
        assert events[0]["title"] == "Team Meeting"
        assert events[0]["external_id"] == "gmail:msg1"

    def test_fetches_inbox_and_starred(self, db, mock_service):
        aid = db.add_account("user@gmail.com", "google", "gmail.readonly")
        mock_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1"}],
        }
        mock_service.users().messages().get().execute.return_value = _make_message(
            "msg1", "Test", "Body"
        )

        syncer = GmailSyncer(db)
        syncer.fetch_recent_messages(mock_service, max_results=10)

        # Verify list was called at least twice (inbox + starred)
        assert mock_service.users().messages().list.call_count >= 2
