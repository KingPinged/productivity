import logging
from datetime import datetime, timezone, timedelta

from src.planner.db import PlannerDB
from src.planner.reminders.notifier import Notifier

logger = logging.getLogger(__name__)

REMINDER_TITLES = {
    "event": "Upcoming Event",
    "task_start": "Time to Start",
    "deadline": "Deadline Warning",
    "break": "Break Time",
    "nudge": "Still Working?",
    "summary": "Daily Summary",
}


class ReminderService:
    """Generate and fire reminders based on schedule, events, and tasks."""

    def __init__(self, db: PlannerDB, notifier: Notifier | None = None):
        self._db = db
        self._notifier = notifier or Notifier()

    def generate_reminders_for_date(self, date: str) -> int:
        """Generate reminders from schedule blocks and events for a given date. Returns count."""
        self._db.clear_reminders_for_date(date)
        blocks = self._db.get_schedule_blocks(date)
        count = 0

        for block in blocks:
            if block["status"] in ("completed", "skipped", "rescheduled"):
                continue

            remind_at = f"{date}T{block['start_time']}:00Z"

            if block["block_type"] == "rest":
                self._db.add_reminder(
                    remind_at=remind_at,
                    reminder_type="break",
                    message=f"Take a break ({block['start_time']} — {block['end_time']})",
                    schedule_block_id=block["id"],
                )
            else:
                reason = block.get("ai_reason") or block["block_type"]
                self._db.add_reminder(
                    remind_at=remind_at,
                    reminder_type="task_start",
                    message=f"Time to start: {reason}",
                    schedule_block_id=block["id"],
                )
            count += 1

        # Generate "upcoming event" reminders (30 min + 5 min before)
        next_day = self._date_offset(date, 1)
        events = self._db.get_events(start_after=date, end_before=next_day)
        for event in events:
            if not event["start_time"]:
                continue
            try:
                evt_time = datetime.fromisoformat(event["start_time"].replace("Z", "+00:00"))
                # 30 min before
                warn_30 = evt_time - timedelta(minutes=30)
                if warn_30 > datetime.now(timezone.utc):
                    self._db.add_reminder(
                        remind_at=warn_30.isoformat(),
                        reminder_type="event",
                        message=f"{event['title']} in 30 minutes",
                    )
                    count += 1
                # 5 min before
                warn_5 = evt_time - timedelta(minutes=5)
                if warn_5 > datetime.now(timezone.utc):
                    self._db.add_reminder(
                        remind_at=warn_5.isoformat(),
                        reminder_type="event",
                        message=f"{event['title']} in 5 minutes",
                        urgent=True,
                    )
                    count += 1
            except ValueError:
                continue

        return count

    def _date_offset(self, date: str, days: int) -> str:
        dt = datetime.strptime(date, "%Y-%m-%d")
        return (dt + timedelta(days=days)).strftime("%Y-%m-%d")

    def generate_deadline_reminders(self) -> int:
        """Generate deadline warning reminders for pending tasks. Returns count."""
        tasks = self._db.get_tasks(status="pending")
        count = 0

        for task in tasks:
            if not task["deadline"]:
                continue

            try:
                deadline = datetime.fromisoformat(task["deadline"].replace("Z", "+00:00"))
            except ValueError:
                continue

            now = datetime.now(timezone.utc)

            # 24h before deadline
            warn_24h = deadline - timedelta(hours=24)
            if warn_24h > now:
                self._db.add_reminder(
                    remind_at=warn_24h.isoformat(),
                    reminder_type="deadline",
                    message=f"{task['title']} due in 24 hours",
                    task_id=task["id"],
                    urgent=False,
                )
                count += 1

            # 3h before deadline
            warn_3h = deadline - timedelta(hours=3)
            if warn_3h > now:
                self._db.add_reminder(
                    remind_at=warn_3h.isoformat(),
                    reminder_type="deadline",
                    message=f"{task['title']} due in 3 hours!",
                    task_id=task["id"],
                    urgent=True,
                )
                count += 1

        return count

    def check_and_fire(self, current_time: str | None = None) -> int:
        """Check for due reminders and fire them. Returns count fired."""
        if current_time is None:
            current_time = datetime.now(timezone.utc).isoformat()

        due = self._db.get_due_reminders(current_time)
        fired = 0

        for reminder in due:
            if self._is_quiet_hours(reminder):
                if not reminder["urgent"]:
                    continue  # Suppress non-urgent during quiet hours

            title = REMINDER_TITLES.get(reminder["reminder_type"], "Reminder")
            self._notifier.send(
                title=title,
                message=reminder["message"],
                reminder_type=reminder["reminder_type"],
            )

            subscriptions = self._db.get_push_subscriptions()
            if subscriptions:
                self._notifier.send_web_push(title, reminder["message"], subscriptions)

            self._db.mark_reminder_fired(reminder["id"])
            fired += 1

        return fired

    def _is_quiet_hours(self, reminder: dict) -> bool:
        """Check if current time falls within quiet hours."""
        start = self._db.get_preference("quiet_hours_start")
        end = self._db.get_preference("quiet_hours_end")
        if not start or not end:
            return False

        try:
            remind_time = reminder["remind_at"]
            # Extract HH:MM from ISO timestamp
            if "T" in remind_time:
                time_part = remind_time.split("T")[1][:5]
            else:
                return False

            # Simple string comparison works for HH:MM format
            if start > end:
                # Quiet hours span midnight (e.g., 23:00 to 07:00)
                return time_part >= start or time_part < end
            else:
                return start <= time_part < end
        except (IndexError, ValueError):
            return False
