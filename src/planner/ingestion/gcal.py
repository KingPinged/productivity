import json
from datetime import datetime, timezone, timedelta

from src.planner.db import PlannerDB


class GCalSyncer:
    def __init__(self, db: PlannerDB):
        self._db = db

    def sync_account(self, account_id: int, service) -> int:
        calendars = service.calendarList().list().execute()
        total = 0
        for cal in calendars.get("items", []):
            cal_id = cal["id"]
            total += self._sync_calendar(account_id, service, cal_id)
        now = datetime.now(timezone.utc).isoformat()
        self._db.update_account_last_sync(account_id, now)
        return total

    def _sync_calendar(self, account_id: int, service, calendar_id: str) -> int:
        count = 0
        page_token = None
        time_min = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        while True:
            kwargs = {
                "calendarId": calendar_id,
                "singleEvents": True,
                "orderBy": "startTime",
                "maxResults": 250,
                "timeMin": time_min,
            }
            if page_token:
                kwargs["pageToken"] = page_token

            result = service.events().list(**kwargs).execute()

            for item in result.get("items", []):
                changed = self._upsert_event(account_id, calendar_id, item)
                if changed:
                    count += 1

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return count

    def _upsert_event(self, account_id: int, calendar_id: str, item: dict) -> bool:
        """Upsert a calendar event. Returns True if data actually changed."""
        event_id = item.get("id", "")
        external_id = f"gcal:{calendar_id}:{event_id}"

        start = item.get("start", {})
        end = item.get("end", {})

        is_all_day = "date" in start
        start_time = start.get("date") or start.get("dateTime")
        end_time = end.get("date") or end.get("dateTime")

        result = self._db.upsert_event(
            account_id=account_id,
            source="gcal",
            external_id=external_id,
            title=item.get("summary", "(No title)"),
            description=item.get("description"),
            start_time=start_time,
            end_time=end_time,
            all_day=is_all_day,
            location=item.get("location"),
            event_type="meeting",
            raw_data=json.dumps(item),
        )
        return result != 0  # 0 means no change
