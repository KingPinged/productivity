import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.planner.db import PlannerDB
from src.planner.ingestion.gcal import GCalSyncer


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = PlannerDB(path)
    database.initialize()
    yield database
    database.close()
    os.unlink(path)


@pytest.fixture
def mock_service():
    service = MagicMock()
    return service


class TestGCalSyncer:
    def test_sync_stores_events_in_db(self, db, mock_service):
        aid = db.add_account("user@gmail.com", "google", "calendar.readonly")
        mock_service.calendarList().list().execute.return_value = {
            "items": [{"id": "primary", "summary": "My Calendar"}]
        }
        mock_service.events().list().execute.return_value = {
            "items": [
                {
                    "id": "evt1",
                    "summary": "Team Standup",
                    "start": {"dateTime": "2026-03-20T09:00:00-05:00"},
                    "end": {"dateTime": "2026-03-20T09:30:00-05:00"},
                    "location": "Zoom",
                    "description": "Daily standup",
                },
            ],
            "nextPageToken": None,
        }

        syncer = GCalSyncer(db)
        count = syncer.sync_account(aid, mock_service)

        assert count == 1
        events = db.get_events(source="gcal")
        assert len(events) == 1
        assert events[0]["title"] == "Team Standup"
        assert events[0]["external_id"] == "gcal:primary:evt1"
        assert events[0]["location"] == "Zoom"

    def test_sync_handles_all_day_events(self, db, mock_service):
        aid = db.add_account("user@gmail.com", "google", "calendar.readonly")
        mock_service.calendarList().list().execute.return_value = {
            "items": [{"id": "primary", "summary": "My Calendar"}]
        }
        mock_service.events().list().execute.return_value = {
            "items": [
                {
                    "id": "evt2",
                    "summary": "Holiday",
                    "start": {"date": "2026-03-25"},
                    "end": {"date": "2026-03-26"},
                },
            ],
            "nextPageToken": None,
        }

        syncer = GCalSyncer(db)
        count = syncer.sync_account(aid, mock_service)

        assert count == 1
        events = db.get_events(source="gcal")
        assert events[0]["all_day"] == 1
        assert events[0]["title"] == "Holiday"

    def test_sync_deduplicates_on_resync(self, db, mock_service):
        aid = db.add_account("user@gmail.com", "google", "calendar.readonly")
        mock_service.calendarList().list().execute.return_value = {
            "items": [{"id": "cal1", "summary": "Cal"}]
        }
        mock_service.events().list().execute.return_value = {
            "items": [
                {
                    "id": "evt1",
                    "summary": "Meeting v1",
                    "start": {"dateTime": "2026-03-20T10:00:00Z"},
                    "end": {"dateTime": "2026-03-20T11:00:00Z"},
                },
            ],
            "nextPageToken": None,
        }

        syncer = GCalSyncer(db)
        syncer.sync_account(aid, mock_service)

        mock_service.events().list().execute.return_value["items"][0]["summary"] = "Meeting v2"
        syncer.sync_account(aid, mock_service)

        events = db.get_events(source="gcal")
        assert len(events) == 1
        assert events[0]["title"] == "Meeting v2"

    def test_sync_multiple_calendars(self, db, mock_service):
        aid = db.add_account("user@gmail.com", "google", "calendar.readonly")
        mock_service.calendarList().list().execute.return_value = {
            "items": [
                {"id": "cal1", "summary": "Personal"},
                {"id": "cal2", "summary": "School"},
            ]
        }

        def events_side_effect(*args, **kwargs):
            mock_resp = MagicMock()
            cal_id = kwargs.get("calendarId", args[0] if args else "cal1")
            if "cal1" in str(cal_id):
                mock_resp.execute.return_value = {
                    "items": [{"id": "e1", "summary": "Personal Event",
                               "start": {"dateTime": "2026-03-20T10:00:00Z"},
                               "end": {"dateTime": "2026-03-20T11:00:00Z"}}],
                    "nextPageToken": None,
                }
            else:
                mock_resp.execute.return_value = {
                    "items": [{"id": "e2", "summary": "School Event",
                               "start": {"dateTime": "2026-03-20T12:00:00Z"},
                               "end": {"dateTime": "2026-03-20T13:00:00Z"}}],
                    "nextPageToken": None,
                }
            return mock_resp

        mock_service.events().list = events_side_effect
        syncer = GCalSyncer(db)
        count = syncer.sync_account(aid, mock_service)

        assert count == 2
        events = db.get_events(source="gcal")
        assert len(events) == 2
