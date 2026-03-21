import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from src.planner.db import PlannerDB
from src.planner.reminders.notifier import Notifier

logger = logging.getLogger(__name__)

CT = ZoneInfo("America/Chicago")

REMINDER_TITLES = {
    "event": "Upcoming Event",
    "task_start": "Time to Start",
    "deadline": "Deadline Warning",
    "break": "Break Time",
    "nudge": "Still Working?",
    "summary": "Daily Summary",
}


def _to_12h(time_str: str) -> str:
    """Convert HH:MM to 12h format."""
    try:
        h, m = time_str.split(":")
        h = int(h)
        ampm = "AM" if h < 12 else "PM"
        if h == 0: h = 12
        elif h > 12: h -= 12
        return f"{h}:{m} {ampm}"
    except Exception:
        return time_str


def _ct_timestamp(date: str, time_str: str) -> str:
    """Create a Central Time ISO timestamp from date + HH:MM.
    Returns UTC ISO string for correct comparison."""
    try:
        dt = datetime.strptime(f"{date}T{time_str}:00", "%Y-%m-%dT%H:%M:%S")
        ct_dt = dt.replace(tzinfo=CT)
        utc_dt = ct_dt.astimezone(timezone.utc)
        return utc_dt.isoformat()
    except Exception:
        return f"{date}T{time_str}:00Z"


class ReminderService:
    """Generate and fire reminders based on schedule, events, and tasks."""

    def __init__(self, db: PlannerDB, notifier: Notifier | None = None):
        self._db = db
        self._notifier = notifier or Notifier()

    def generate_reminders_for_date(self, date: str) -> int:
        """Generate reminders from schedule blocks and events for a given date. Returns count."""
        self._db.clear_reminders_for_date(date)
        blocks = self._db.get_schedule_blocks(date)
        now = datetime.now(timezone.utc)
        count = 0

        for block in blocks:
            if block["status"] in ("completed", "skipped", "rescheduled"):
                continue

            # Convert block time to proper UTC timestamp (blocks are in Central Time)
            remind_at = _ct_timestamp(date, block["start_time"])
            start_12 = _to_12h(block["start_time"])
            end_12 = _to_12h(block["end_time"])

            # Skip if already past
            try:
                if datetime.fromisoformat(remind_at) < now:
                    continue
            except Exception:
                pass

            if block["block_type"] == "rest":
                self._db.add_reminder(
                    remind_at=remind_at,
                    reminder_type="break",
                    message=f"Take a break ({start_12} - {end_12})",
                    schedule_block_id=block["id"],
                )
            else:
                reason = block.get("ai_reason") or block["block_type"]
                self._db.add_reminder(
                    remind_at=remind_at,
                    reminder_type="task_start",
                    message=f"{reason} ({start_12} - {end_12})",
                    schedule_block_id=block["id"],
                )

                # 10-minute advance reminder for important blocks (study, meeting)
                if block["block_type"] in ("study", "meeting"):
                    try:
                        block_time = datetime.fromisoformat(remind_at)
                        warn_10 = block_time - timedelta(minutes=10)
                        if warn_10 > now:
                            self._db.add_reminder(
                                remind_at=warn_10.isoformat(),
                                reminder_type="event",
                                message=f"Starting in 10 min: {reason}",
                                schedule_block_id=block["id"],
                            )
                            count += 1
                    except Exception:
                        pass

            count += 1

        # Generate reminders for calendar events
        next_day = self._date_offset(date, 1)
        events = self._db.get_events(start_after=date, end_before=next_day)
        for event in events:
            if not event["start_time"]:
                continue
            try:
                evt_time = datetime.fromisoformat(event["start_time"].replace("Z", "+00:00"))
                if evt_time.tzinfo is None:
                    evt_time = evt_time.replace(tzinfo=CT).astimezone(timezone.utc)

                # 10 min before (important events)
                warn_10 = evt_time - timedelta(minutes=10)
                if warn_10 > now:
                    self._db.add_reminder(
                        remind_at=warn_10.isoformat(),
                        reminder_type="event",
                        message=f"{event['title']} in 10 minutes",
                        urgent=True,
                    )
                    count += 1

                # 30 min before
                warn_30 = evt_time - timedelta(minutes=30)
                if warn_30 > now:
                    self._db.add_reminder(
                        remind_at=warn_30.isoformat(),
                        reminder_type="event",
                        message=f"{event['title']} in 30 minutes",
                    )
                    count += 1
            except (ValueError, TypeError):
                continue

        return count

    def _date_offset(self, date: str, days: int) -> str:
        dt = datetime.strptime(date, "%Y-%m-%d")
        return (dt + timedelta(days=days)).strftime("%Y-%m-%d")

    def generate_deadline_reminders(self) -> int:
        """Generate deadline warning reminders for pending tasks."""
        tasks = self._db.get_tasks(status="pending")
        now = datetime.now(timezone.utc)
        count = 0

        for task in tasks:
            if not task["deadline"]:
                continue

            try:
                deadline_str = task["deadline"].replace("Z", "+00:00")
                deadline = datetime.fromisoformat(deadline_str)
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=CT).astimezone(timezone.utc)
            except (ValueError, TypeError):
                continue

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

            # 1h before deadline
            warn_1h = deadline - timedelta(hours=1)
            if warn_1h > now:
                self._db.add_reminder(
                    remind_at=warn_1h.isoformat(),
                    reminder_type="deadline",
                    message=f"URGENT: {task['title']} due in 1 hour!",
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
                    continue

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
            logger.info("Fired reminder: [%s] %s", reminder["reminder_type"], reminder["message"][:50])

        return fired

    def _is_quiet_hours(self, reminder: dict) -> bool:
        """Check if current time in CT falls within quiet hours."""
        start = self._db.get_preference("quiet_hours_start")
        end = self._db.get_preference("quiet_hours_end")
        if not start or not end:
            return False

        now_ct = datetime.now(CT)
        current_hhmm = now_ct.strftime("%H:%M")

        if start > end:
            return current_hhmm >= start or current_hhmm < end
        else:
            return start <= current_hhmm < end
