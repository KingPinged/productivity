# AI Scheduling Assistant — Phase 6: Reminders & Notifications

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reminder service that fires system notifications with sound for upcoming events, task starts, deadline warnings, breaks, nudges, and daily summaries.

**Architecture:** A `ReminderService` runs in the background via APScheduler, checking every 30 seconds for reminders that need to fire. Reminders are generated from schedule blocks (task start, break), events (upcoming meeting), and tasks (deadline warnings). The system uses `plyer` for cross-platform native notifications and bundled `.wav` files for sounds. A nudge system checks the usage tracker endpoint to detect if the user is on an unproductive app during a study block. Quiet hours suppress non-urgent reminders. New API endpoints expose pending reminders and allow dismissal/snoozing.

**Tech Stack:** `plyer` (notifications), `playsound` or `winsound` (audio), APScheduler, FastAPI

**Spec:** `docs/superpowers/specs/2026-03-19-ai-scheduling-assistant-design.md` (Section 6)

**Depends on:** Phase 1-5 (all backend + UI)

---

## File Structure

### New Python Files

| File | Responsibility |
|------|---------------|
| `src/planner/reminders/__init__.py` | Package init |
| `src/planner/reminders/service.py` | ReminderService: generate reminders from schedule/events/tasks, check and fire on schedule |
| `src/planner/reminders/notifier.py` | Cross-platform notification dispatch (plyer) + sound playback |
| `src/planner/reminders/assets/chime.wav` | Gentle chime sound for upcoming events |
| `src/planner/reminders/assets/tone.wav` | Medium tone for task start |
| `src/planner/reminders/assets/urgent.wav` | Urgent tone for deadline warnings |
| `src/planner/reminders/assets/bell.wav` | Soft bell for break reminders |
| `src/planner/reminders/assets/ping.wav` | Gentle ping for nudges |
| `src/planner/api/reminders.py` | Reminder API routes: GET /api/reminders, PATCH /api/reminders/:id |

### Modified Python Files

| File | Change |
|------|--------|
| `src/planner/db.py` | Add reminder CRUD methods |
| `src/planner/server.py` | Register reminder routes, init reminder service |
| `requirements.txt` | Add plyer |

### New Frontend Files

| File | Responsibility |
|------|---------------|
| `frontend/src/components/ReminderToast.tsx` | In-app reminder display toast |
| `frontend/src/hooks/useReminders.ts` | Reminder polling + dismiss |

### Modified Frontend Files

| File | Change |
|------|--------|
| `frontend/src/App.tsx` | Add ReminderToast overlay |
| `frontend/src/components/SettingsView.tsx` | Add quiet hours + nudge toggle preferences |

### Test Files

| File | Tests |
|------|-------|
| `tests/planner/test_db_reminders.py` | Reminder CRUD |
| `tests/planner/test_reminder_service.py` | Reminder generation and firing logic |
| `tests/planner/test_reminder_routes.py` | Reminder API endpoints |

---

## Task 1: Add Dependencies + Sound Assets

**Files:**
- Modify: `requirements.txt`
- Create: `src/planner/reminders/__init__.py`
- Create: `src/planner/reminders/assets/` (directory with placeholder sounds)

- [ ] **Step 1: Add plyer to requirements.txt**

Append to `requirements.txt`:
```
plyer>=2.1.0
```

- [ ] **Step 2: Install**

Run: `pip install plyer`

- [ ] **Step 3: Create reminder package and sound assets**

Create `src/planner/reminders/__init__.py` (empty).

Create the assets directory and generate minimal `.wav` files using Python:
```python
# Run this once to generate placeholder sound files
import struct, wave, os, math

assets_dir = "src/planner/reminders/assets"
os.makedirs(assets_dir, exist_ok=True)

def make_wav(filename, freq=440, duration_ms=500, volume=0.5):
    sample_rate = 44100
    n_samples = int(sample_rate * duration_ms / 1000)
    with wave.open(os.path.join(assets_dir, filename), 'w') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        for i in range(n_samples):
            t = i / sample_rate
            val = int(volume * 32767 * math.sin(2 * math.pi * freq * t))
            # Apply fade out in last 20%
            if i > n_samples * 0.8:
                val = int(val * (n_samples - i) / (n_samples * 0.2))
            f.writeframes(struct.pack('<h', val))

make_wav("chime.wav", freq=523, duration_ms=300, volume=0.3)
make_wav("tone.wav", freq=440, duration_ms=500, volume=0.5)
make_wav("urgent.wav", freq=880, duration_ms=800, volume=0.7)
make_wav("bell.wav", freq=392, duration_ms=400, volume=0.3)
make_wav("ping.wav", freq=660, duration_ms=200, volume=0.3)
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt src/planner/reminders/
git commit -m "chore: add plyer dependency and sound assets for reminders"
```

---

## Task 2: Database Reminder CRUD

**Files:**
- Modify: `src/planner/db.py`
- Create: `tests/planner/test_db_reminders.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_db_reminders.py`:
```python
import os
import tempfile
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

class TestReminderCRUD:
    def test_add_reminder(self, db):
        rid = db.add_reminder(
            remind_at="2026-03-20T08:30:00Z",
            reminder_type="task_start",
            message="Time to start: Calculus PS4",
        )
        assert rid > 0

    def test_add_reminder_with_block(self, db):
        bid = db.add_schedule_block(
            date="2026-03-20", start_time="09:00", end_time="10:00", block_type="study",
        )
        rid = db.add_reminder(
            remind_at="2026-03-20T09:00:00Z",
            reminder_type="task_start",
            message="Time to study",
            schedule_block_id=bid,
        )
        reminders = db.get_pending_reminders()
        assert len(reminders) == 1
        assert reminders[0]["schedule_block_id"] == bid

    def test_get_pending_reminders(self, db):
        db.add_reminder(
            remind_at="2026-03-20T08:00:00Z", reminder_type="task_start",
            message="Task 1",
        )
        db.add_reminder(
            remind_at="2026-03-20T09:00:00Z", reminder_type="break",
            message="Take a break",
        )
        reminders = db.get_pending_reminders()
        assert len(reminders) == 2

    def test_get_pending_excludes_fired(self, db):
        rid = db.add_reminder(
            remind_at="2026-03-20T08:00:00Z", reminder_type="task_start",
            message="Task 1",
        )
        db.mark_reminder_fired(rid)
        assert db.get_pending_reminders() == []

    def test_mark_reminder_fired(self, db):
        rid = db.add_reminder(
            remind_at="2026-03-20T08:00:00Z", reminder_type="event",
            message="Meeting soon",
        )
        db.mark_reminder_fired(rid)
        reminders = db.get_pending_reminders()
        assert len(reminders) == 0

    def test_get_due_reminders(self, db):
        db.add_reminder(
            remind_at="2026-03-20T08:00:00Z", reminder_type="task_start",
            message="Past reminder",
        )
        db.add_reminder(
            remind_at="2099-12-31T23:59:00Z", reminder_type="event",
            message="Future reminder",
        )
        due = db.get_due_reminders("2026-03-20T10:00:00Z")
        assert len(due) == 1
        assert due[0]["message"] == "Past reminder"

    def test_dismiss_reminder(self, db):
        rid = db.add_reminder(
            remind_at="2026-03-20T08:00:00Z", reminder_type="event",
            message="Meeting",
        )
        db.mark_reminder_fired(rid)
        assert len(db.get_pending_reminders()) == 0

    def test_clear_reminders_for_date(self, db):
        db.add_reminder(
            remind_at="2026-03-20T08:00:00Z", reminder_type="task_start",
            message="Today's reminder",
        )
        db.add_reminder(
            remind_at="2026-03-21T08:00:00Z", reminder_type="task_start",
            message="Tomorrow's reminder",
        )
        db.clear_reminders_for_date("2026-03-20")
        reminders = db.get_pending_reminders()
        assert len(reminders) == 1
        assert reminders[0]["message"] == "Tomorrow's reminder"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_db_reminders.py -v`
Expected: FAIL

- [ ] **Step 3: Implement reminder CRUD**

Add to `src/planner/db.py`:
```python
# --- Reminder CRUD ---

def add_reminder(
    self,
    remind_at: str,
    reminder_type: str,
    message: str,
    schedule_block_id: int | None = None,
    task_id: int | None = None,
    urgent: bool = False,
) -> int:
    conn = self._get_conn()
    cursor = conn.execute(
        """INSERT INTO reminders (schedule_block_id, task_id, remind_at,
           reminder_type, message, urgent)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (schedule_block_id, task_id, remind_at, reminder_type, message, int(urgent)),
    )
    conn.commit()
    return cursor.lastrowid

def get_pending_reminders(self) -> list[dict]:
    conn = self._get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM reminders WHERE fired = 0 ORDER BY remind_at"
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.row_factory = None
    return rows

def get_due_reminders(self, current_time: str) -> list[dict]:
    conn = self._get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM reminders WHERE fired = 0 AND remind_at <= ? ORDER BY remind_at",
        (current_time,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.row_factory = None
    return rows

def mark_reminder_fired(self, reminder_id: int) -> None:
    conn = self._get_conn()
    conn.execute(
        "UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,)
    )
    conn.commit()

def clear_reminders_for_date(self, date: str) -> None:
    conn = self._get_conn()
    conn.execute(
        "DELETE FROM reminders WHERE remind_at LIKE ?", (f"{date}%",)
    )
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_db_reminders.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/planner/db.py tests/planner/test_db_reminders.py
git commit -m "feat(planner): add reminder CRUD methods to database"
```

---

## Task 3: Notification Dispatcher

**Files:**
- Create: `src/planner/reminders/notifier.py`

- [ ] **Step 1: Implement Notifier**

Create `src/planner/reminders/notifier.py`:
```python
import logging
import platform
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent / "assets"

SOUND_MAP = {
    "event": "chime.wav",
    "task_start": "tone.wav",
    "deadline": "urgent.wav",
    "break": "bell.wav",
    "nudge": "ping.wav",
    "summary": None,  # No sound for daily summary
}


class Notifier:
    """Cross-platform notification + sound dispatcher."""

    def send(self, title: str, message: str, reminder_type: str = "event") -> None:
        """Send a system notification with optional sound."""
        # Fire sound in background thread (non-blocking)
        sound_file = SOUND_MAP.get(reminder_type)
        if sound_file:
            threading.Thread(
                target=self._play_sound,
                args=(sound_file,),
                daemon=True,
            ).start()

        # Send system notification
        try:
            self._send_notification(title, message)
        except Exception as e:
            logger.warning("Failed to send notification: %s", e)

    def _send_notification(self, title: str, message: str) -> None:
        """Send a native system notification."""
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message,
                app_name="Productivity Planner",
                timeout=10,
            )
        except Exception as e:
            logger.warning("plyer notification failed: %s", e)
            # Fallback: try platform-specific
            if platform.system() == "Windows":
                self._windows_fallback(title, message)

    def _play_sound(self, filename: str) -> None:
        """Play a .wav sound file."""
        sound_path = ASSETS_DIR / filename
        if not sound_path.exists():
            return

        try:
            if platform.system() == "Windows":
                import winsound
                winsound.PlaySound(str(sound_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                # macOS / Linux fallback
                import subprocess
                if platform.system() == "Darwin":
                    subprocess.Popen(["afplay", str(sound_path)])
                else:
                    subprocess.Popen(["aplay", "-q", str(sound_path)])
        except Exception as e:
            logger.warning("Failed to play sound %s: %s", filename, e)

    def _windows_fallback(self, title: str, message: str) -> None:
        """Windows fallback using win10toast or ctypes."""
        try:
            import ctypes
            ctypes.windll.user32.MessageBeep(0)
        except Exception:
            pass
```

- [ ] **Step 2: Commit**

```bash
git add src/planner/reminders/notifier.py
git commit -m "feat(planner): add cross-platform notification dispatcher with sound playback"
```

---

## Task 4: Reminder Service

**Files:**
- Create: `src/planner/reminders/service.py`
- Create: `tests/planner/test_reminder_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_reminder_service.py`:
```python
import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.planner.db import PlannerDB
from src.planner.reminders.service import ReminderService


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
def mock_notifier():
    return MagicMock()


class TestReminderService:
    def test_generate_block_reminders(self, db, mock_notifier):
        db.add_schedule_block(
            date="2026-03-20", start_time="09:00", end_time="10:30",
            block_type="study", ai_reason="Calculus due tomorrow",
        )
        db.add_schedule_block(
            date="2026-03-20", start_time="10:30", end_time="10:45",
            block_type="rest",
        )

        service = ReminderService(db, mock_notifier)
        service.generate_reminders_for_date("2026-03-20")

        reminders = db.get_pending_reminders()
        # Should have: task_start for study block + break for rest block
        types = {r["reminder_type"] for r in reminders}
        assert "task_start" in types
        assert "break" in types

    def test_generate_deadline_reminders(self, db, mock_notifier):
        db.upsert_task(
            source="canvas", external_id="t1", title="Calculus PS4",
            deadline="2026-03-21T23:59:00Z",
        )

        service = ReminderService(db, mock_notifier)
        service.generate_deadline_reminders()

        reminders = db.get_pending_reminders()
        deadline_reminders = [r for r in reminders if r["reminder_type"] == "deadline"]
        assert len(deadline_reminders) >= 1

    def test_fire_due_reminders(self, db, mock_notifier):
        db.add_reminder(
            remind_at="2026-03-20T08:00:00Z",
            reminder_type="task_start",
            message="Time to start studying",
        )

        service = ReminderService(db, mock_notifier)
        service.check_and_fire("2026-03-20T08:01:00Z")

        mock_notifier.send.assert_called_once()
        assert db.get_pending_reminders() == []

    def test_quiet_hours_suppress_non_urgent(self, db, mock_notifier):
        db.set_preference("quiet_hours_start", "23:00")
        db.set_preference("quiet_hours_end", "07:00")

        db.add_reminder(
            remind_at="2026-03-20T02:00:00Z",
            reminder_type="task_start",
            message="Non-urgent during quiet hours",
        )

        service = ReminderService(db, mock_notifier)
        service.check_and_fire("2026-03-20T02:01:00Z")

        mock_notifier.send.assert_not_called()

    def test_urgent_fires_during_quiet_hours(self, db, mock_notifier):
        db.set_preference("quiet_hours_start", "23:00")
        db.set_preference("quiet_hours_end", "07:00")

        db.add_reminder(
            remind_at="2026-03-20T02:00:00Z",
            reminder_type="deadline",
            message="Assignment due in 3 hours!",
            urgent=True,
        )

        service = ReminderService(db, mock_notifier)
        service.check_and_fire("2026-03-20T02:01:00Z")

        mock_notifier.send.assert_called_once()

    def test_does_not_double_fire(self, db, mock_notifier):
        db.add_reminder(
            remind_at="2026-03-20T08:00:00Z",
            reminder_type="event",
            message="Meeting",
        )

        service = ReminderService(db, mock_notifier)
        service.check_and_fire("2026-03-20T08:01:00Z")
        service.check_and_fire("2026-03-20T08:02:00Z")

        assert mock_notifier.send.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_reminder_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement ReminderService**

Create `src/planner/reminders/service.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_reminder_service.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/planner/reminders/service.py tests/planner/test_reminder_service.py
git commit -m "feat(planner): add reminder service with generation, quiet hours, and firing logic"
```

---

## Task 5: Reminder API Routes

**Files:**
- Create: `src/planner/api/reminders.py`
- Create: `tests/planner/test_reminder_routes.py`
- Modify: `src/planner/server.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_reminder_routes.py`:
```python
import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from src.planner.db import PlannerDB
from src.planner.server import create_app

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
    app = create_app(db_path=db_path, auth_token=token)
    with TestClient(app) as c:
        yield c

@pytest.fixture
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def seeded_db(db_path):
    db = PlannerDB(db_path)
    db.initialize()
    db.add_reminder(
        remind_at="2026-03-20T08:00:00Z", reminder_type="task_start",
        message="Start studying",
    )
    db.add_reminder(
        remind_at="2026-03-20T10:00:00Z", reminder_type="break",
        message="Take a break",
    )
    db.close()

class TestReminderRoutes:
    def test_get_pending_reminders(self, client, auth_headers, seeded_db):
        resp = client.get("/api/reminders", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_dismiss_reminder(self, client, auth_headers, seeded_db):
        resp = client.get("/api/reminders", headers=auth_headers)
        rid = resp.json()[0]["id"]
        resp = client.patch(
            f"/api/reminders/{rid}",
            json={"action": "dismiss"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        resp = client.get("/api/reminders", headers=auth_headers)
        assert len(resp.json()) == 1

    def test_reminders_require_auth(self, client):
        assert client.get("/api/reminders").status_code == 401
```

- [ ] **Step 2: Implement reminder routes**

Create `src/planner/api/reminders.py`:
```python
from fastapi import APIRouter, Depends
from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")

def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")

@router.get("/reminders")
def list_reminders(db: PlannerDB = Depends(get_db)):
    return db.get_pending_reminders()

@router.patch("/reminders/{reminder_id}")
def update_reminder(reminder_id: int, body: dict, db: PlannerDB = Depends(get_db)):
    action = body.get("action", "dismiss")
    if action == "dismiss":
        db.mark_reminder_fired(reminder_id)
    return {"status": "ok"}
```

- [ ] **Step 3: Register in server.py**

Add import:
```python
from src.planner.api import reminders as reminders_module
from src.planner.reminders.service import ReminderService
from src.planner.reminders.notifier import Notifier
```

Add in `create_app` AFTER the SyncScheduler is created and started (after `sync_module.sync_callback = scheduler.sync_all`) and after task routes:
```python
# Reminder routes and service
app.dependency_overrides[reminders_module.get_db] = get_db
for route in reminders_module.router.routes:
    route.dependencies = [require_token]
app.include_router(reminders_module.router)

# Reminder service (check every 30 seconds)
notifier = Notifier()
reminder_service = ReminderService(db, notifier)
scheduler._scheduler.add_job(
    reminder_service.check_and_fire,
    "interval",
    seconds=30,
    id="check_reminders",
    replace_existing=True,
)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/planner/test_reminder_routes.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/planner/api/reminders.py src/planner/server.py tests/planner/test_reminder_routes.py
git commit -m "feat(planner): add reminder API routes and wire service to scheduler"
```

---

## Task 6: Frontend Reminder Toast + Settings

**Files:**
- Create: `frontend/src/hooks/useReminders.ts`
- Create: `frontend/src/components/ReminderToast.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/SettingsView.tsx`

- [ ] **Step 1: Create reminder hook**

Create `frontend/src/hooks/useReminders.ts`:
```typescript
import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'

interface Reminder {
  id: number
  remind_at: string
  reminder_type: string
  message: string
  urgent: boolean
  fired: boolean
}

export function useReminders() {
  const [reminders, setReminders] = useState<Reminder[]>([])

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<Reminder[]>('/api/reminders')
      setReminders(data)
    } catch (err) {
      console.error('Failed to load reminders:', err)
    }
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 30000) // Poll every 30s
    return () => clearInterval(interval)
  }, [load])

  const dismiss = useCallback(async (id: number) => {
    await apiFetch(`/api/reminders/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ action: 'dismiss' }),
    })
    setReminders(prev => prev.filter(r => r.id !== id))
  }, [])

  // Get reminders that are due now (remind_at <= current time)
  const dueReminders = reminders.filter(r => {
    const remindAt = new Date(r.remind_at)
    return remindAt <= new Date() && !r.fired
  })

  return { reminders: dueReminders, dismiss, reload: load }
}
```

- [ ] **Step 2: Create ReminderToast component**

Create `frontend/src/components/ReminderToast.tsx`:
```tsx
import { useReminders } from '../hooks/useReminders'

const TYPE_COLORS: Record<string, string> = {
  event: 'border-green-500',
  task_start: 'border-blue-500',
  deadline: 'border-red-500',
  break: 'border-amber-500',
  nudge: 'border-purple-500',
  summary: 'border-gray-500',
}

const TYPE_ICONS: Record<string, string> = {
  event: '\u{1F4C5}',
  task_start: '\u25B6',
  deadline: '\u26A0',
  break: '\u2615',
  nudge: '\u{1F914}',
  summary: '\u2600',
}

export default function ReminderToast() {
  const { reminders, dismiss } = useReminders()

  if (reminders.length === 0) return null

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 max-w-sm">
      {reminders.map(reminder => (
        <div
          key={reminder.id}
          className={`bg-surface-light border-l-4 ${TYPE_COLORS[reminder.reminder_type] || 'border-gray-500'} rounded-lg p-4 shadow-xl animate-pulse-once`}
        >
          <div className="flex items-start gap-3">
            <span className="text-lg flex-shrink-0">
              {TYPE_ICONS[reminder.reminder_type] || '\u{1F514}'}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-white text-sm font-medium">{reminder.message}</p>
              <p className="text-gray-400 text-xs mt-1">
                {new Date(reminder.remind_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </p>
            </div>
            <button
              onClick={() => dismiss(reminder.id)}
              className="text-gray-500 hover:text-white text-sm flex-shrink-0"
            >
              {'\u2715'}
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 3: Add ReminderToast to App.tsx**

In `frontend/src/App.tsx`, add import:
```tsx
import ReminderToast from './components/ReminderToast'
```

Add `<ReminderToast />` inside the root div, after `<main>`:
```tsx
return (
    <div className="flex h-screen bg-surface">
      <Sidebar currentView={view} onNavigate={setView} />
      <main className="flex-1 overflow-auto p-6">
        {/* ... existing view rendering ... */}
      </main>
      <ReminderToast />
    </div>
  )
```

- [ ] **Step 4: Add quiet hours + nudge preferences to SettingsView**

In `frontend/src/components/SettingsView.tsx`, add these fields to the `FIELDS` array:
```typescript
{ key: 'quiet_hours_start', label: 'Quiet Hours Start', type: 'time', default: '23:00' },
{ key: 'quiet_hours_end', label: 'Quiet Hours End', type: 'time', default: '07:00' },
{ key: 'nudge_enabled', label: 'Nudge System', type: 'select', default: 'enabled', options: ['enabled', 'disabled'] },
```

- [ ] **Step 5: Build frontend**

Run: `cd frontend && npm run build`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/ frontend/dist/
git commit -m "feat(frontend): add reminder toasts, notification settings, and quiet hours preferences"
```

---

## Task 7: Run All Tests and Final Build

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/planner/ -v`
Expected: All tests pass

- [ ] **Step 2: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit if needed**

```bash
git add frontend/dist/
git commit -m "chore: final frontend build with Phase 6 reminders"
```
