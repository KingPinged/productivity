import hashlib
import json
from datetime import datetime, timedelta
from src.planner.db import PlannerDB


class ContextBuilder:
    def __init__(self, db: PlannerDB):
        self._db = db

    def build(self, date: str) -> dict:
        prefs = self._db.get_all_preferences()
        events = self._db.get_events(
            start_after=date,
            end_before=self._date_offset(date, 7),
        )
        tasks = self._db.get_tasks(status="pending")
        all_blocks = self._db.get_schedule_blocks(date)
        completed = [b for b in all_blocks if b["status"] == "completed"]

        return {
            "date": date,
            "day_of_week": self._day_of_week(date),
            "events": [
                {
                    "title": e["title"],
                    "start_time": e["start_time"],
                    "end_time": e["end_time"],
                    "event_type": e["event_type"],
                    "source": e["source"],
                    "all_day": bool(e["all_day"]),
                }
                for e in events
            ],
            "tasks": [
                {
                    "id": t["id"],
                    "title": t["title"],
                    "course": t["course"],
                    "deadline": t["deadline"],
                    "estimated_minutes": t["estimated_minutes"],
                    "priority": t["priority"],
                    "current_grade": t["current_grade"],
                    "grade_weight": t["grade_weight"],
                    "source": t["source"],
                }
                for t in tasks
            ],
            "completed_today": [
                {
                    "block_type": b["block_type"],
                    "start_time": b["start_time"],
                    "end_time": b["end_time"],
                }
                for b in completed
            ],
            "preferences": prefs,
        }

    def compute_hash(self, context: dict) -> str:
        serialized = json.dumps(context, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]

    def _date_offset(self, date: str, days: int) -> str:
        dt = datetime.strptime(date, "%Y-%m-%d")
        return (dt + timedelta(days=days)).strftime("%Y-%m-%d")

    def _day_of_week(self, date: str) -> str:
        dt = datetime.strptime(date, "%Y-%m-%d")
        return dt.strftime("%A")
