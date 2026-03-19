# AI Scheduling Assistant — Phase 4: AI Scheduling Engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Claude-powered AI scheduling engine that autonomously generates and maintains a time-blocked daily schedule from all ingested data sources.

**Architecture:** A context builder gathers all data (events, tasks, grades, usage patterns, preferences) into a structured prompt. A scheduler module calls Claude API with this context and parses the structured JSON response into schedule blocks. A replan endpoint triggers on-demand replanning. The schedule API (stub from Phase 1) is upgraded to serve real AI-generated blocks. Error handling includes JSON validation, overlap detection, fallback to last valid schedule, and exponential backoff retries.

**Tech Stack:** `anthropic` (Claude API SDK), FastAPI, SQLite

**Spec:** `docs/superpowers/specs/2026-03-19-ai-scheduling-assistant-design.md` (Section 4)

**Depends on:** Phase 1 (DB, server, schedule API stub), Phase 2 (events, tasks from Gmail/GCal), Phase 3 (tasks from Canvas)

---

## File Structure

### New Python Files

| File | Responsibility |
|------|---------------|
| `src/planner/ai/__init__.py` | Package init |
| `src/planner/ai/context_builder.py` | Gather all data from DB into a structured context dict for Claude |
| `src/planner/ai/prompts.py` | System prompt and user prompt templates for scheduling |
| `src/planner/ai/scheduler.py` | Core scheduler: call Claude API, parse response, validate, store blocks |
| `src/planner/api/tasks.py` | Task API routes: GET/POST/PATCH/DELETE for manual task management |

### Modified Python Files

| File | Change |
|------|--------|
| `src/planner/db.py` | Add schedule_block CRUD, ai_context_cache methods |
| `src/planner/api/schedule.py` | Upgrade stub to serve real blocks and trigger replan |
| `src/planner/server.py` | Register task routes, init scheduler |
| `requirements.txt` | Add anthropic SDK |

### Test Files

| File | Tests |
|------|-------|
| `tests/planner/test_context_builder.py` | Context assembly from DB data |
| `tests/planner/test_scheduler.py` | Schedule generation, JSON validation, overlap detection, error handling |
| `tests/planner/test_db_schedule.py` | Schedule block and AI cache CRUD |
| `tests/planner/test_task_routes.py` | Task API endpoints |
| `tests/planner/test_schedule_routes.py` | Updated schedule endpoints |

---

## Task 1: Add Anthropic SDK

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add anthropic to requirements.txt**

Append to `requirements.txt`:
```
anthropic>=0.40.0
```

- [ ] **Step 2: Install**

Run: `pip install anthropic`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add Anthropic SDK dependency for AI scheduling engine"
```

---

## Task 2: Database Schedule Block and AI Cache CRUD

**Files:**
- Modify: `src/planner/db.py`
- Create: `tests/planner/test_db_schedule.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_db_schedule.py`:
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


class TestScheduleBlockCRUD:
    def test_add_schedule_block(self, db):
        bid = db.add_schedule_block(
            date="2026-03-20",
            start_time="09:00",
            end_time="10:30",
            block_type="study",
            ai_reason="Due tomorrow",
        )
        assert bid > 0

    def test_add_block_with_task(self, db):
        tid = db.upsert_task(source="canvas", external_id="t1", title="HW1")
        bid = db.add_schedule_block(
            date="2026-03-20", start_time="09:00", end_time="10:30",
            block_type="study", task_id=tid,
        )
        blocks = db.get_schedule_blocks("2026-03-20")
        assert len(blocks) == 1
        assert blocks[0]["task_id"] == tid

    def test_get_schedule_blocks_by_date(self, db):
        db.add_schedule_block(date="2026-03-20", start_time="09:00", end_time="10:00", block_type="study")
        db.add_schedule_block(date="2026-03-20", start_time="10:15", end_time="10:30", block_type="rest")
        db.add_schedule_block(date="2026-03-21", start_time="09:00", end_time="10:00", block_type="study")
        blocks = db.get_schedule_blocks("2026-03-20")
        assert len(blocks) == 2

    def test_update_block_status(self, db):
        bid = db.add_schedule_block(
            date="2026-03-20", start_time="09:00", end_time="10:00", block_type="study",
        )
        db.update_block_status(bid, "completed")
        blocks = db.get_schedule_blocks("2026-03-20")
        assert blocks[0]["status"] == "completed"

    def test_clear_schedule_for_date(self, db):
        db.add_schedule_block(date="2026-03-20", start_time="09:00", end_time="10:00", block_type="study")
        db.add_schedule_block(date="2026-03-20", start_time="10:00", end_time="10:15", block_type="rest")
        db.clear_schedule_blocks("2026-03-20")
        assert db.get_schedule_blocks("2026-03-20") == []

    def test_clear_preserves_completed_blocks(self, db):
        bid1 = db.add_schedule_block(date="2026-03-20", start_time="09:00", end_time="10:00", block_type="study")
        bid2 = db.add_schedule_block(date="2026-03-20", start_time="10:00", end_time="11:00", block_type="study")
        db.update_block_status(bid1, "completed")
        db.clear_schedule_blocks("2026-03-20", preserve_completed=True)
        blocks = db.get_schedule_blocks("2026-03-20")
        assert len(blocks) == 1
        assert blocks[0]["status"] == "completed"


class TestAIContextCache:
    def test_save_and_get_cache(self, db):
        db.save_ai_cache("2026-03-20", "hash123", '{"schedule":[]}', 5000)
        cache = db.get_ai_cache("2026-03-20")
        assert cache is not None
        assert cache["context_hash"] == "hash123"
        assert cache["tokens_used"] == 5000

    def test_get_cache_missing(self, db):
        assert db.get_ai_cache("2026-03-20") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_db_schedule.py -v`
Expected: FAIL

- [ ] **Step 3: Implement schedule block and AI cache CRUD**

Add to `src/planner/db.py`:
```python
# --- Schedule Block CRUD ---

def add_schedule_block(
    self,
    date: str,
    start_time: str,
    end_time: str,
    block_type: str,
    task_id: int | None = None,
    ai_reason: str | None = None,
    status: str = "scheduled",
) -> int:
    conn = self._get_conn()
    cursor = conn.execute(
        """INSERT INTO schedule_blocks (task_id, date, start_time, end_time,
           block_type, status, ai_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (task_id, date, start_time, end_time, block_type, status, ai_reason),
    )
    conn.commit()
    return cursor.lastrowid

def get_schedule_blocks(self, date: str) -> list[dict]:
    conn = self._get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM schedule_blocks WHERE date = ? ORDER BY start_time",
        (date,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.row_factory = None
    return rows

def update_block_status(self, block_id: int, status: str) -> None:
    conn = self._get_conn()
    conn.execute(
        "UPDATE schedule_blocks SET status = ? WHERE id = ?", (status, block_id)
    )
    conn.commit()

def clear_schedule_blocks(self, date: str, preserve_completed: bool = False) -> None:
    conn = self._get_conn()
    if preserve_completed:
        conn.execute(
            "DELETE FROM schedule_blocks WHERE date = ? AND status != 'completed'",
            (date,),
        )
    else:
        conn.execute("DELETE FROM schedule_blocks WHERE date = ?", (date,))
    conn.commit()

# --- AI Context Cache ---

def save_ai_cache(self, date: str, context_hash: str, schedule_json: str, tokens_used: int) -> None:
    conn = self._get_conn()
    conn.execute(
        """INSERT INTO ai_context_cache (date, context_hash, schedule_json, tokens_used)
           VALUES (?, ?, ?, ?)""",
        (date, context_hash, schedule_json, tokens_used),
    )
    conn.commit()

def get_ai_cache(self, date: str) -> dict | None:
    conn = self._get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM ai_context_cache WHERE date = ? ORDER BY created_at DESC LIMIT 1",
        (date,),
    )
    row = cursor.fetchone()
    conn.row_factory = None
    return dict(row) if row else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_db_schedule.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/planner/db.py tests/planner/test_db_schedule.py
git commit -m "feat(planner): add schedule block and AI cache CRUD to database"
```

---

## Task 3: Context Builder

**Files:**
- Create: `src/planner/ai/__init__.py`
- Create: `src/planner/ai/context_builder.py`
- Create: `tests/planner/test_context_builder.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_context_builder.py`:
```python
import os
import tempfile
from datetime import datetime, timezone

import pytest

from src.planner.db import PlannerDB
from src.planner.ai.context_builder import ContextBuilder


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
def seeded_db(db):
    """DB with sample data for context building."""
    # Preferences
    db.set_preference("wake_time", "07:00")
    db.set_preference("sleep_time", "23:00")
    db.set_preference("max_work_hours", "8")
    db.set_preference("break_frequency", "90")

    # Account + events
    aid = db.add_account("user@gmail.com", "google", "gmail.readonly")
    db.upsert_event(
        account_id=aid, source="gcal", external_id="evt1",
        title="Team Meeting", start_time="2026-03-20T14:00:00Z",
        end_time="2026-03-20T15:00:00Z", event_type="meeting",
    )

    # Tasks
    db.upsert_task(
        source="canvas", external_id="t1", title="Calculus PS4",
        course="MATH 201", deadline="2026-03-21T23:59:00Z",
        estimated_minutes=90, current_grade="B-",
    )
    db.upsert_task(
        source="canvas", external_id="t2", title="CS Lab Report",
        course="CS 301", deadline="2026-03-25T23:59:00Z",
        estimated_minutes=120, current_grade="A",
    )

    # Completed schedule block
    db.add_schedule_block(
        date="2026-03-20", start_time="08:00", end_time="09:00",
        block_type="study", status="completed",
    )

    return db


class TestContextBuilder:
    def test_build_context_returns_dict(self, seeded_db):
        builder = ContextBuilder(seeded_db)
        ctx = builder.build("2026-03-20")
        assert isinstance(ctx, dict)
        assert "date" in ctx
        assert "events" in ctx
        assert "tasks" in ctx
        assert "preferences" in ctx
        assert "completed_today" in ctx

    def test_context_includes_events(self, seeded_db):
        builder = ContextBuilder(seeded_db)
        ctx = builder.build("2026-03-20")
        assert len(ctx["events"]) >= 1
        assert ctx["events"][0]["title"] == "Team Meeting"

    def test_context_includes_pending_tasks(self, seeded_db):
        builder = ContextBuilder(seeded_db)
        ctx = builder.build("2026-03-20")
        assert len(ctx["tasks"]) == 2
        assert any(t["title"] == "Calculus PS4" for t in ctx["tasks"])

    def test_context_includes_preferences(self, seeded_db):
        builder = ContextBuilder(seeded_db)
        ctx = builder.build("2026-03-20")
        assert ctx["preferences"]["wake_time"] == "07:00"
        assert ctx["preferences"]["sleep_time"] == "23:00"

    def test_context_includes_completed_blocks(self, seeded_db):
        builder = ContextBuilder(seeded_db)
        ctx = builder.build("2026-03-20")
        assert len(ctx["completed_today"]) == 1

    def test_context_hash_changes_with_data(self, seeded_db):
        builder = ContextBuilder(seeded_db)
        hash1 = builder.compute_hash(builder.build("2026-03-20"))
        seeded_db.upsert_task(source="manual", external_id="t3", title="New Task")
        hash2 = builder.compute_hash(builder.build("2026-03-20"))
        assert hash1 != hash2

    def test_context_hash_stable_for_same_data(self, seeded_db):
        builder = ContextBuilder(seeded_db)
        ctx = builder.build("2026-03-20")
        hash1 = builder.compute_hash(ctx)
        hash2 = builder.compute_hash(ctx)
        assert hash1 == hash2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_context_builder.py -v`
Expected: FAIL

- [ ] **Step 3: Implement ContextBuilder**

Create `src/planner/ai/__init__.py` (empty).

Create `src/planner/ai/context_builder.py`:
```python
import hashlib
import json
from datetime import datetime, timedelta

from src.planner.db import PlannerDB


class ContextBuilder:
    """Gather all planner data into a structured context for Claude."""

    def __init__(self, db: PlannerDB):
        self._db = db

    def build(self, date: str) -> dict:
        """Build full scheduling context for a given date."""
        prefs = self._db.get_all_preferences()

        # Events: next 7 days
        events = self._db.get_events(
            start_after=date,
            end_before=self._date_offset(date, 7),
        )

        # Tasks: all pending
        tasks = self._db.get_tasks(status="pending")

        # Completed blocks today
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
        """Compute a deterministic hash of the context for cache comparison."""
        serialized = json.dumps(context, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]

    def _date_offset(self, date: str, days: int) -> str:
        dt = datetime.strptime(date, "%Y-%m-%d")
        return (dt + timedelta(days=days)).strftime("%Y-%m-%d")

    def _day_of_week(self, date: str) -> str:
        dt = datetime.strptime(date, "%Y-%m-%d")
        return dt.strftime("%A")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_context_builder.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/planner/ai/__init__.py src/planner/ai/context_builder.py tests/planner/test_context_builder.py
git commit -m "feat(planner): add context builder for AI scheduling prompts"
```

---

## Task 4: Prompt Templates

**Files:**
- Create: `src/planner/ai/prompts.py`

- [ ] **Step 1: Create prompt templates**

Create `src/planner/ai/prompts.py`:
```python
SYSTEM_PROMPT = """You are an AI scheduling assistant for a college student. Your job is to create an optimal daily schedule as time-blocked entries.

Rules:
1. Schedule within the user's wake/sleep window only.
2. Never overlap blocks with existing calendar events.
3. Insert break blocks: 15 minutes every 90 minutes of work (or per user preference).
4. Prioritize by: deadline proximity × grade impact. Lower grades = more study time.
5. Schedule demanding work during peak hours (typically morning/early afternoon).
6. Place lighter tasks (emails, organizing) in low-energy windows.
7. No block should exceed 2 hours without a break.
8. Account for completed blocks — don't reschedule what's done.

Output ONLY valid JSON matching this schema:
{
  "schedule": [
    {
      "start": "HH:MM",
      "end": "HH:MM",
      "task": "Task name or 'Break'",
      "type": "study|meeting|rest|personal|buffer",
      "priority": "high|medium|low",
      "reason": "Brief explanation"
    }
  ],
  "tasks_today": ["Task names to complete today"],
  "tasks_later": ["Task names deferred to future days"],
  "reminders": [
    {"time": "HH:MM", "message": "Reminder text", "urgent": true/false}
  ]
}

Do not include any text before or after the JSON."""


def build_user_prompt(context: dict) -> str:
    """Build the user prompt from scheduling context."""
    parts = []

    parts.append(f"Today is {context['day_of_week']}, {context['date']}.")

    # Preferences
    prefs = context.get("preferences", {})
    wake = prefs.get("wake_time", "07:00")
    sleep = prefs.get("sleep_time", "23:00")
    max_hours = prefs.get("max_work_hours", "8")
    break_freq = prefs.get("break_frequency", "90")
    style = prefs.get("schedule_style", "balanced")

    parts.append(f"\nSchedule window: {wake} to {sleep}")
    parts.append(f"Max work hours: {max_hours}")
    parts.append(f"Break every {break_freq} minutes")
    parts.append(f"Schedule style: {style}")

    # Existing calendar events (immovable)
    events = context.get("events", [])
    if events:
        parts.append("\n## Fixed Calendar Events (do not schedule over these):")
        for e in events:
            parts.append(f"- {e['title']}: {e['start_time']} to {e['end_time']} ({e['event_type']})")

    # Tasks
    tasks = context.get("tasks", [])
    if tasks:
        parts.append("\n## Pending Tasks:")
        for t in tasks:
            line = f"- {t['title']}"
            if t.get("course"):
                line += f" [{t['course']}]"
            if t.get("deadline"):
                line += f" — due {t['deadline']}"
            if t.get("estimated_minutes"):
                line += f" (~{t['estimated_minutes']} min)"
            if t.get("current_grade"):
                line += f" (current grade: {t['current_grade']})"
            parts.append(line)

    # Completed today
    completed = context.get("completed_today", [])
    if completed:
        parts.append("\n## Already Completed Today:")
        for c in completed:
            parts.append(f"- {c['block_type']}: {c['start_time']} to {c['end_time']}")

    parts.append("\nCreate an optimized schedule for the rest of today.")

    return "\n".join(parts)
```

- [ ] **Step 2: Commit**

```bash
git add src/planner/ai/prompts.py
git commit -m "feat(planner): add system and user prompt templates for AI scheduling"
```

---

## Task 5: AI Scheduler Core

**Files:**
- Create: `src/planner/ai/scheduler.py`
- Create: `tests/planner/test_scheduler.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_scheduler.py`:
```python
import json
import os
import tempfile
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from src.planner.db import PlannerDB
from src.planner.ai.scheduler import AIScheduler


VALID_RESPONSE = json.dumps({
    "schedule": [
        {"start": "09:00", "end": "10:30", "task": "Calculus PS4", "type": "study", "priority": "high", "reason": "Due tomorrow"},
        {"start": "10:30", "end": "10:45", "task": "Break", "type": "rest", "priority": "low", "reason": "Scheduled break"},
        {"start": "10:45", "end": "12:00", "task": "CS Lab Report", "type": "study", "priority": "medium", "reason": "Due in 5 days"},
    ],
    "tasks_today": ["Calculus PS4", "CS Lab Report"],
    "tasks_later": ["History essay"],
    "reminders": [{"time": "13:30", "message": "Team meeting in 30 min", "urgent": True}],
})

OVERLAPPING_RESPONSE = json.dumps({
    "schedule": [
        {"start": "09:00", "end": "10:30", "task": "Task A", "type": "study", "priority": "high", "reason": "test"},
        {"start": "10:00", "end": "11:00", "task": "Task B", "type": "study", "priority": "medium", "reason": "overlaps"},
    ],
    "tasks_today": [], "tasks_later": [], "reminders": [],
})


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = PlannerDB(path)
    database.initialize()
    database.set_preference("wake_time", "07:00")
    database.set_preference("sleep_time", "23:00")
    yield database
    database.close()
    os.unlink(path)


@pytest.fixture
def mock_client():
    client = MagicMock()
    return client


class TestAIScheduler:
    def test_parse_valid_response(self, db):
        scheduler = AIScheduler(db, api_key="fake")
        result = scheduler.parse_response(VALID_RESPONSE)
        assert len(result["schedule"]) == 3
        assert result["schedule"][0]["task"] == "Calculus PS4"
        assert result["tasks_today"] == ["Calculus PS4", "CS Lab Report"]

    def test_parse_invalid_json_returns_none(self, db):
        scheduler = AIScheduler(db, api_key="fake")
        result = scheduler.parse_response("not json at all")
        assert result is None

    def test_parse_missing_schedule_key_returns_none(self, db):
        scheduler = AIScheduler(db, api_key="fake")
        result = scheduler.parse_response('{"tasks_today": []}')
        assert result is None

    def test_detect_overlapping_blocks(self, db):
        scheduler = AIScheduler(db, api_key="fake")
        result = scheduler.parse_response(OVERLAPPING_RESPONSE)
        assert result is not None
        assert scheduler.has_overlaps(result["schedule"])

    def test_no_overlaps_in_valid_schedule(self, db):
        scheduler = AIScheduler(db, api_key="fake")
        result = scheduler.parse_response(VALID_RESPONSE)
        assert not scheduler.has_overlaps(result["schedule"])

    def test_store_schedule_blocks(self, db):
        scheduler = AIScheduler(db, api_key="fake")
        result = scheduler.parse_response(VALID_RESPONSE)
        scheduler.store_schedule("2026-03-20", result)
        blocks = db.get_schedule_blocks("2026-03-20")
        assert len(blocks) == 3
        assert blocks[0]["block_type"] == "study"
        assert blocks[0]["start_time"] == "09:00"

    def test_store_clears_existing_non_completed(self, db):
        db.add_schedule_block(date="2026-03-20", start_time="08:00", end_time="09:00", block_type="study")
        completed_id = db.add_schedule_block(
            date="2026-03-20", start_time="07:00", end_time="08:00",
            block_type="study", status="completed",
        )
        scheduler = AIScheduler(db, api_key="fake")
        result = scheduler.parse_response(VALID_RESPONSE)
        scheduler.store_schedule("2026-03-20", result)
        blocks = db.get_schedule_blocks("2026-03-20")
        # 1 completed (preserved) + 3 new
        assert len(blocks) == 4

    def test_generate_calls_claude(self, db, mock_client):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=VALID_RESPONSE)]
        mock_response.usage.input_tokens = 1000
        mock_response.usage.output_tokens = 500
        mock_client.messages.create.return_value = mock_response

        scheduler = AIScheduler(db, api_key="fake")
        scheduler._client = mock_client
        result = scheduler.generate("2026-03-20")
        assert result is not None
        assert len(result["schedule"]) == 3
        mock_client.messages.create.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_scheduler.py -v`
Expected: FAIL

- [ ] **Step 3: Implement AIScheduler**

Create `src/planner/ai/scheduler.py`:
```python
import json
import logging
import time

import anthropic

from src.planner.ai.context_builder import ContextBuilder
from src.planner.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from src.planner.db import PlannerDB

logger = logging.getLogger(__name__)

REQUIRED_KEYS = {"schedule", "tasks_today", "tasks_later", "reminders"}
MAX_RETRIES = 2
BACKOFF_DELAYS = [5, 15, 60]


class AIScheduler:
    """Core AI scheduling engine using Claude API."""

    def __init__(self, db: PlannerDB, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self._db = db
        self._api_key = api_key
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)
        self._context_builder = ContextBuilder(db)

    def generate(self, date: str) -> dict | None:
        """Generate a full schedule for the given date. Returns parsed result or None."""
        context = self._context_builder.build(date)
        context_hash = self._context_builder.compute_hash(context)

        # Check cache — skip if context hasn't changed
        cached = self._db.get_ai_cache(date)
        if cached and cached["context_hash"] == context_hash:
            logger.info("Context unchanged for %s, using cached schedule", date)
            try:
                return json.loads(cached["schedule_json"])
            except Exception:
                pass

        base_prompt = build_user_prompt(context)

        for attempt in range(MAX_RETRIES + 1):
            try:
                # Build prompt with retry prefix if needed (fresh each attempt)
                retry_prefix = ""
                if attempt > 0:
                    retry_prefix = "IMPORTANT: Your previous response had issues. "

                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": retry_prefix + base_prompt}],
                )

                raw_text = response.content[0].text
                tokens_used = response.usage.input_tokens + response.usage.output_tokens

                result = self.parse_response(raw_text)
                if result is None:
                    if attempt < MAX_RETRIES:
                        logger.warning("Invalid JSON from Claude, retrying (%d/%d)", attempt + 1, MAX_RETRIES)
                        continue
                    logger.error("Failed to get valid JSON after %d attempts", MAX_RETRIES + 1)
                    return None

                if self.has_overlaps(result["schedule"]):
                    if attempt < MAX_RETRIES:
                        logger.warning("Schedule has overlaps, retrying (%d/%d)", attempt + 1, MAX_RETRIES)
                        continue
                    logger.warning("Schedule still has overlaps after retries, accepting anyway")

                # Cache the result
                self._db.save_ai_cache(date, context_hash, json.dumps(result), tokens_used)
                return result

            except anthropic.RateLimitError:
                delay = BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)]
                logger.warning("Rate limited, backing off %ds", delay)
                time.sleep(delay)
            except anthropic.APIError as e:
                logger.error("Claude API error: %s", e)
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)])
                    continue
                return None

        return None

    def replan(self, date: str) -> dict | None:
        """Force a replan for the given date, ignoring cache. Stores result in DB."""
        context = self._context_builder.build(date)
        context_hash = self._context_builder.compute_hash(context)
        user_prompt = build_user_prompt(context)

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw_text = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens

            result = self.parse_response(raw_text)
            if result is None:
                return None

            self._db.save_ai_cache(date, context_hash, json.dumps(result), tokens_used)
            self.store_schedule(date, result)
            return result

        except Exception as e:
            logger.error("Replan failed: %s", e)
            return None

    def parse_response(self, raw_text: str) -> dict | None:
        """Parse and validate Claude's JSON response."""
        try:
            # Strip markdown code fences if present
            text = raw_text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None

        if not isinstance(data, dict):
            return None
        if "schedule" not in data:
            return None
        if not isinstance(data["schedule"], list):
            return None

        # Ensure required keys with defaults
        data.setdefault("tasks_today", [])
        data.setdefault("tasks_later", [])
        data.setdefault("reminders", [])

        return data

    def has_overlaps(self, schedule: list[dict]) -> bool:
        """Check if any schedule blocks overlap."""
        sorted_blocks = sorted(schedule, key=lambda b: b.get("start", ""))
        for i in range(1, len(sorted_blocks)):
            prev_end = sorted_blocks[i - 1].get("end", "")
            curr_start = sorted_blocks[i].get("start", "")
            if prev_end > curr_start:
                return True
        return False

    def store_schedule(self, date: str, result: dict) -> None:
        """Store schedule blocks in the DB, preserving completed blocks."""
        self._db.clear_schedule_blocks(date, preserve_completed=True)

        # Build a name->id lookup for pending tasks to link blocks to tasks
        pending_tasks = self._db.get_tasks(status="pending")
        task_name_map = {t["title"].lower(): t["id"] for t in pending_tasks}

        for block in result.get("schedule", []):
            # Try to match block's task name to a DB task
            task_name = block.get("task", "")
            task_id = task_name_map.get(task_name.lower()) if task_name else None

            self._db.add_schedule_block(
                date=date,
                start_time=block.get("start", ""),
                end_time=block.get("end", ""),
                block_type=block.get("type", "buffer"),
                task_id=task_id,
                ai_reason=block.get("reason"),
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_scheduler.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/planner/ai/scheduler.py tests/planner/test_scheduler.py
git commit -m "feat(planner): add AI scheduler with Claude API, validation, overlap detection, and caching"
```

---

## Task 6: Upgrade Schedule API and Add Replan Endpoint

**Files:**
- Modify: `src/planner/api/schedule.py`
- Create: `tests/planner/test_schedule_routes.py`
- Modify: `src/planner/server.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_schedule_routes.py`:
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
    db.add_schedule_block(
        date="2026-03-20", start_time="09:00", end_time="10:30",
        block_type="study", ai_reason="Due tomorrow",
    )
    db.add_schedule_block(
        date="2026-03-20", start_time="10:30", end_time="10:45",
        block_type="rest",
    )
    db.close()


class TestScheduleRoutes:
    def test_get_schedule_returns_blocks(self, client, auth_headers, seeded_db):
        resp = client.get("/api/schedule/2026-03-20", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["date"] == "2026-03-20"
        assert len(data["blocks"]) == 2
        assert data["blocks"][0]["block_type"] == "study"

    def test_get_schedule_empty_date(self, client, auth_headers):
        resp = client.get("/api/schedule/2026-03-25", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["blocks"] == []

    def test_update_block_status(self, client, auth_headers, seeded_db):
        # Get the first block's ID
        resp = client.get("/api/schedule/2026-03-20", headers=auth_headers)
        block_id = resp.json()["blocks"][0]["id"]

        resp = client.patch(
            f"/api/schedule/{block_id}",
            json={"status": "completed"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        resp = client.get("/api/schedule/2026-03-20", headers=auth_headers)
        block = [b for b in resp.json()["blocks"] if b["id"] == block_id][0]
        assert block["status"] == "completed"

    def test_schedule_requires_auth(self, client):
        assert client.get("/api/schedule/2026-03-20").status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_schedule_routes.py -v`
Expected: FAIL

- [ ] **Step 3: Upgrade schedule API**

Replace `src/planner/api/schedule.py`:
```python
from fastapi import APIRouter, Depends

from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")

# Module-level reference, set by server.py
ai_scheduler = None


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


@router.get("/schedule/{date}")
def get_schedule(date: str, db: PlannerDB = Depends(get_db)):
    """Get schedule blocks for a date."""
    blocks = db.get_schedule_blocks(date)
    return {"date": date, "blocks": blocks}


@router.patch("/schedule/{block_id}")
def update_block(block_id: int, body: dict, db: PlannerDB = Depends(get_db)):
    """Update a schedule block (status, move, etc.)."""
    if "status" in body:
        db.update_block_status(block_id, body["status"])
    return {"status": "updated"}


@router.post("/schedule/replan")
def trigger_replan(body: dict | None = None, db: PlannerDB = Depends(get_db)):
    """Trigger AI replan for a date."""
    from datetime import date as date_type
    target_date = (body or {}).get("date", date_type.today().isoformat())

    if ai_scheduler is None:
        return {"error": "AI scheduler not configured. Set ANTHROPIC_API_KEY in preferences."}

    result = ai_scheduler.replan(target_date)
    if result is None:
        return {"status": "failed", "message": "AI scheduling failed. Check API key and try again."}

    ai_scheduler.store_schedule(target_date, result)
    return {"status": "ok", "blocks_count": len(result.get("schedule", []))}
```

- [ ] **Step 4: Wire up AI scheduler in server.py**

Add to `src/planner/server.py` imports:
```python
from src.planner.ai.scheduler import AIScheduler
```

Add in `create_app`, after the canvas scraper setup:
```python
# AI Scheduler setup
anthropic_key = db.get_preference("anthropic_api_key")
if anthropic_key:
    ai_sched = AIScheduler(db, api_key=anthropic_key)
    schedule_module.ai_scheduler = ai_sched

    # Morning generation: schedule daily plan at wake time
    wake_time = db.get_preference("wake_time", "07:00")
    hour, minute = (int(x) for x in wake_time.split(":"))
    scheduler.add_morning_job(ai_sched, hour, minute)
```

Also add to `SyncScheduler` a method for morning planning (in `src/planner/ingestion/sync_scheduler.py`):
```python
def add_morning_job(self, ai_scheduler, hour: int, minute: int) -> None:
    """Schedule daily morning plan generation."""
    from datetime import date

    def morning_plan():
        today = date.today().isoformat()
        ai_scheduler.generate(today)
        result_cached = ai_scheduler._db.get_ai_cache(today)
        if result_cached:
            import json
            result = json.loads(result_cached["schedule_json"])
            ai_scheduler.store_schedule(today, result)

    self._scheduler.add_job(
        morning_plan, "cron", hour=hour, minute=minute,
        id="morning_plan", replace_existing=True,
    )
```

Note: Continuous replanning (triggered by data changes like new emails or completed tasks) is handled via the manual `POST /schedule/replan` endpoint for now. Fully automated continuous replanning (event-driven triggers) is deferred to Phase 5/6 when the UI can detect user interactions and fire replans automatically.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_schedule_routes.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/planner/api/schedule.py src/planner/server.py tests/planner/test_schedule_routes.py
git commit -m "feat(planner): upgrade schedule API with real blocks, status updates, and replan endpoint"
```

---

## Task 7: Task API Routes

**Files:**
- Create: `src/planner/api/tasks.py`
- Create: `tests/planner/test_task_routes.py`
- Modify: `src/planner/server.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_task_routes.py`:
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
    db.upsert_task(source="canvas", external_id="t1", title="HW1", course="CS 101", deadline="2026-03-25T23:59:00Z")
    db.upsert_task(source="manual", external_id="t2", title="Buy groceries", status="pending")
    db.close()


class TestTaskRoutes:
    def test_list_tasks(self, client, auth_headers, seeded_db):
        resp = client.get("/api/tasks", headers=auth_headers)
        assert resp.status_code == 200
        tasks = resp.json()
        assert len(tasks) == 2

    def test_filter_tasks_by_source(self, client, auth_headers, seeded_db):
        resp = client.get("/api/tasks?source=canvas", headers=auth_headers)
        tasks = resp.json()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "HW1"

    def test_filter_tasks_by_status(self, client, auth_headers, seeded_db):
        resp = client.get("/api/tasks?status=pending", headers=auth_headers)
        tasks = resp.json()
        assert len(tasks) == 2

    def test_create_manual_task(self, client, auth_headers):
        resp = client.post(
            "/api/tasks",
            json={"title": "Study for exam", "deadline": "2026-03-30T14:00:00Z"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["task_id"] > 0

        resp = client.get("/api/tasks", headers=auth_headers)
        assert len(resp.json()) == 1

    def test_update_task_status(self, client, auth_headers, seeded_db):
        resp = client.get("/api/tasks", headers=auth_headers)
        task_id = resp.json()[0]["id"]

        resp = client.patch(
            f"/api/tasks/{task_id}",
            json={"status": "done"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_delete_task(self, client, auth_headers, seeded_db):
        resp = client.get("/api/tasks", headers=auth_headers)
        task_id = resp.json()[0]["id"]

        resp = client.delete(f"/api/tasks/{task_id}", headers=auth_headers)
        assert resp.status_code == 200

    def test_tasks_require_auth(self, client):
        assert client.get("/api/tasks").status_code == 401
```

- [ ] **Step 2: Implement task routes**

Create `src/planner/api/tasks.py`:
```python
import secrets
from fastapi import APIRouter, Depends, Query

from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


@router.get("/tasks")
def list_tasks(
    source: str | None = Query(None),
    status: str | None = Query(None),
    db: PlannerDB = Depends(get_db),
):
    return db.get_tasks(source=source, status=status)


@router.post("/tasks")
def create_task(body: dict, db: PlannerDB = Depends(get_db)):
    """Create a manual task."""
    task_id = db.upsert_task(
        source="manual",
        external_id=f"manual:{secrets.token_urlsafe(8)}",
        title=body.get("title", "Untitled"),
        description=body.get("description"),
        course=body.get("course"),
        deadline=body.get("deadline"),
        estimated_minutes=body.get("estimated_minutes"),
        priority=body.get("priority", 3),
    )
    return {"task_id": task_id}


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, body: dict, db: PlannerDB = Depends(get_db)):
    """Update task fields."""
    if "status" in body:
        db.update_task_status(task_id, body["status"])
    return {"status": "updated"}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: PlannerDB = Depends(get_db)):
    """Delete a task by marking as skipped."""
    db.update_task_status(task_id, "skipped")
    return {"status": "deleted"}
```

- [ ] **Step 3: Register in server.py**

Add import:
```python
from src.planner.api import tasks as tasks_module
```

Add after canvas setup:
```python
# Task routes
app.dependency_overrides[tasks_module.get_db] = get_db
for route in tasks_module.router.routes:
    route.dependencies = [require_token]
app.include_router(tasks_module.router)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/planner/test_task_routes.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/planner/api/tasks.py src/planner/server.py tests/planner/test_task_routes.py
git commit -m "feat(planner): add task API routes for manual task management"
```

---

## Task 8: Run All Tests

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/planner/ -v`
Expected: All tests pass

- [ ] **Step 2: Fix any failures**

- [ ] **Step 3: Commit if fixes were needed**

```bash
git commit -m "fix: resolve test failures from Phase 4 integration"
```
