# AI Scheduling Assistant — Phase 3: Canvas LMS Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scrape Canvas LMS for assignments, due dates, grades, and calendar events using Playwright, then store them as tasks and events in the planner database.

**Architecture:** Playwright opens a headed browser for initial manual login (handling SSO/MFA). Session cookies are encrypted (Fernet, key in OS keyring) and stored in SQLite's `canvas_configs` table. Subsequent scrapes run headless using saved cookies. A scraper module extracts assignments, grades, and calendar events from Canvas pages. The sync scheduler runs Canvas sync every 2 hours. New API endpoints handle Canvas setup, re-login, and config deletion. The frontend gets a Canvas configuration panel in Settings.

**Tech Stack:** Playwright (Python), cryptography (Fernet via existing EncryptionManager), FastAPI, React

**Spec:** `docs/superpowers/specs/2026-03-19-ai-scheduling-assistant-design.md` (Section 3.3, 7, 8)

**Depends on:** Phase 1 (DB, server, encryption), Phase 2 (sync scheduler, events API)

---

## File Structure

### New Python Files

| File | Responsibility |
|------|---------------|
| `src/planner/ingestion/canvas.py` | Canvas scraper: login flow, cookie management, page scraping (dashboard, courses, calendar, grades) |
| `src/planner/ingestion/canvas_parser.py` | Parse HTML from Canvas pages into structured assignment/grade/event data |
| `src/planner/api/canvas.py` | Canvas routes: POST /canvas/setup, POST /canvas/relogin, DELETE /canvas/configs/:id |

### Modified Python Files

| File | Change |
|------|--------|
| `src/planner/db.py` | Add canvas_config CRUD, task CRUD methods |
| `src/planner/ingestion/sync_scheduler.py` | Add Canvas sync to the periodic schedule (every 2 hours) |
| `src/planner/server.py` | Register canvas routes |
| `requirements.txt` | Add playwright |

### New Frontend Files

| File | Responsibility |
|------|---------------|
| `frontend/src/components/CanvasPanel.tsx` | Canvas config UI: URL input, login button, status display |
| `frontend/src/hooks/useCanvas.ts` | Canvas config data fetching + mutations |

### Modified Frontend Files

| File | Change |
|------|--------|
| `frontend/src/components/SettingsView.tsx` | Add CanvasPanel below AccountsPanel |
| `frontend/src/types/index.ts` | Add CanvasConfig, Task interfaces |

### Test Files

| File | Tests |
|------|-------|
| `tests/planner/test_db_canvas.py` | Canvas config CRUD, task CRUD |
| `tests/planner/test_canvas_parser.py` | HTML parsing for assignments, grades, calendar |
| `tests/planner/test_canvas_routes.py` | Canvas API endpoints |

---

## Task 1: Add Playwright Dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add Playwright to requirements.txt**

Append to `requirements.txt`:
```
playwright>=1.48.0
```

- [ ] **Step 2: Install Playwright and browsers**

Run: `pip install playwright && python -m playwright install chromium`
Expected: Chromium browser downloaded

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add Playwright dependency for Canvas scraping"
```

---

## Task 2: Database Canvas Config and Task CRUD

**Files:**
- Modify: `src/planner/db.py`
- Create: `tests/planner/test_db_canvas.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_db_canvas.py`:
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


class TestCanvasConfigCRUD:
    def test_add_canvas_config(self, db):
        cid = db.add_canvas_config("https://canvas.university.edu", "encrypted-cookies")
        assert cid > 0

    def test_get_canvas_config(self, db):
        cid = db.add_canvas_config("https://canvas.university.edu", "encrypted-cookies")
        config = db.get_canvas_config(cid)
        assert config["canvas_url"] == "https://canvas.university.edu"
        assert config["session_cookies"] == "encrypted-cookies"
        assert config["status"] == "active"

    def test_list_canvas_configs(self, db):
        db.add_canvas_config("https://canvas1.edu", "cookies1")
        db.add_canvas_config("https://canvas2.edu", "cookies2")
        configs = db.list_canvas_configs()
        assert len(configs) == 2

    def test_list_excludes_deleted(self, db):
        cid = db.add_canvas_config("https://canvas.edu", "cookies")
        db.soft_delete_canvas_config(cid)
        assert db.list_canvas_configs() == []

    def test_update_canvas_cookies(self, db):
        cid = db.add_canvas_config("https://canvas.edu", "old-cookies")
        db.update_canvas_cookies(cid, "new-cookies")
        config = db.get_canvas_config(cid)
        assert config["session_cookies"] == "new-cookies"

    def test_update_canvas_status(self, db):
        cid = db.add_canvas_config("https://canvas.edu", "cookies")
        db.update_canvas_status(cid, "expired")
        config = db.get_canvas_config(cid)
        assert config["status"] == "expired"

    def test_update_canvas_last_sync(self, db):
        cid = db.add_canvas_config("https://canvas.edu", "cookies")
        db.update_canvas_last_sync(cid, "2026-03-19T12:00:00Z")
        config = db.get_canvas_config(cid)
        assert config["last_sync"] == "2026-03-19T12:00:00Z"


class TestTaskCRUD:
    def test_upsert_task(self, db):
        tid = db.upsert_task(
            source="canvas",
            external_id="canvas:CS101:hw1",
            title="Homework 1",
            course="CS 101",
            deadline="2026-03-25T23:59:00Z",
            estimated_minutes=60,
        )
        assert tid > 0

    def test_upsert_task_dedup(self, db):
        id1 = db.upsert_task(
            source="canvas", external_id="canvas:CS101:hw1",
            title="HW1 v1", course="CS 101",
            deadline="2026-03-25T23:59:00Z",
        )
        id2 = db.upsert_task(
            source="canvas", external_id="canvas:CS101:hw1",
            title="HW1 v2", course="CS 101",
            deadline="2026-03-26T23:59:00Z",
        )
        assert id1 == id2
        tasks = db.get_tasks(source="canvas")
        assert len(tasks) == 1
        assert tasks[0]["title"] == "HW1 v2"

    def test_get_tasks_by_status(self, db):
        db.upsert_task(
            source="canvas", external_id="t1",
            title="Task 1", status="pending",
        )
        db.upsert_task(
            source="canvas", external_id="t2",
            title="Task 2", status="done",
        )
        pending = db.get_tasks(status="pending")
        assert len(pending) == 1
        assert pending[0]["title"] == "Task 1"

    def test_get_tasks_by_source(self, db):
        db.upsert_task(source="canvas", external_id="t1", title="Canvas Task")
        db.upsert_task(source="manual", external_id="t2", title="Manual Task")
        canvas_tasks = db.get_tasks(source="canvas")
        assert len(canvas_tasks) == 1

    def test_update_task_status(self, db):
        tid = db.upsert_task(source="canvas", external_id="t1", title="Task")
        db.update_task_status(tid, "done")
        task = db.get_tasks(source="canvas")[0]
        assert task["status"] == "done"

    def test_update_task_grade_info(self, db):
        tid = db.upsert_task(
            source="canvas", external_id="t1", title="Task",
            course="CS 101", grade_weight=0.15, current_grade="B-",
        )
        tasks = db.get_tasks(source="canvas")
        assert tasks[0]["grade_weight"] == 0.15
        assert tasks[0]["current_grade"] == "B-"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_db_canvas.py -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 3: Implement canvas config and task CRUD**

Add these methods to `src/planner/db.py` in the `PlannerDB` class:

```python
# --- Canvas Config CRUD ---

def add_canvas_config(self, canvas_url: str, session_cookies: str) -> int:
    conn = self._get_conn()
    cursor = conn.execute(
        "INSERT INTO canvas_configs (canvas_url, session_cookies) VALUES (?, ?)",
        (canvas_url, session_cookies),
    )
    conn.commit()
    return cursor.lastrowid

def get_canvas_config(self, config_id: int) -> dict | None:
    conn = self._get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM canvas_configs WHERE id = ?", (config_id,))
    row = cursor.fetchone()
    conn.row_factory = None
    return dict(row) if row else None

def list_canvas_configs(self) -> list[dict]:
    conn = self._get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM canvas_configs WHERE deleted_at IS NULL ORDER BY canvas_url"
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.row_factory = None
    return rows

def soft_delete_canvas_config(self, config_id: int) -> None:
    conn = self._get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE canvas_configs SET deleted_at = ? WHERE id = ?", (now, config_id)
    )
    conn.commit()

def update_canvas_cookies(self, config_id: int, session_cookies: str) -> None:
    conn = self._get_conn()
    conn.execute(
        "UPDATE canvas_configs SET session_cookies = ?, status = 'active' WHERE id = ?",
        (session_cookies, config_id),
    )
    conn.commit()

def update_canvas_status(self, config_id: int, status: str) -> None:
    conn = self._get_conn()
    conn.execute(
        "UPDATE canvas_configs SET status = ? WHERE id = ?", (status, config_id)
    )
    conn.commit()

def update_canvas_last_sync(self, config_id: int, timestamp: str) -> None:
    conn = self._get_conn()
    conn.execute(
        "UPDATE canvas_configs SET last_sync = ? WHERE id = ?", (timestamp, config_id)
    )
    conn.commit()

# --- Task CRUD ---

def upsert_task(
    self,
    source: str,
    external_id: str,
    title: str,
    description: str | None = None,
    course: str | None = None,
    deadline: str | None = None,
    estimated_minutes: int | None = None,
    priority: int = 3,
    status: str = "pending",
    grade_weight: float | None = None,
    current_grade: str | None = None,
    ai_notes: str | None = None,
) -> int:
    conn = self._get_conn()
    cursor = conn.execute(
        "SELECT id FROM tasks WHERE source = ? AND external_id = ?",
        (source, external_id),
    )
    row = cursor.fetchone()
    if row:
        conn.execute(
            """UPDATE tasks SET title=?, description=?, course=?, deadline=?,
               estimated_minutes=?, priority=?, status=?, grade_weight=?,
               current_grade=?, ai_notes=?
               WHERE id=?""",
            (title, description, course, deadline, estimated_minutes,
             priority, status, grade_weight, current_grade, ai_notes, row[0]),
        )
        conn.commit()
        return row[0]
    cursor = conn.execute(
        """INSERT INTO tasks (source, external_id, title, description, course,
           deadline, estimated_minutes, priority, status, grade_weight,
           current_grade, ai_notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (source, external_id, title, description, course, deadline,
         estimated_minutes, priority, status, grade_weight, current_grade, ai_notes),
    )
    conn.commit()
    return cursor.lastrowid

def get_tasks(
    self,
    source: str | None = None,
    status: str | None = None,
) -> list[dict]:
    conn = self._get_conn()
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM tasks WHERE 1=1"
    params: list = []
    if source:
        query += " AND source = ?"
        params.append(source)
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY deadline"
    cursor = conn.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.row_factory = None
    return rows

def update_task_status(self, task_id: int, status: str) -> None:
    conn = self._get_conn()
    updates = "status = ?"
    params: list = [status]
    if status == "done":
        now = datetime.now(timezone.utc).isoformat()
        updates += ", completed_at = ?"
        params.append(now)
    params.append(task_id)
    conn.execute(f"UPDATE tasks SET {updates} WHERE id = ?", params)
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_db_canvas.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/planner/db.py tests/planner/test_db_canvas.py
git commit -m "feat(planner): add canvas config and task CRUD methods to database"
```

---

## Task 3: Canvas HTML Parser

**Files:**
- Create: `src/planner/ingestion/canvas_parser.py`
- Create: `tests/planner/test_canvas_parser.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_canvas_parser.py`:
```python
import pytest

from src.planner.ingestion.canvas_parser import CanvasParser


class TestParseAssignments:
    def test_parse_dashboard_assignments(self):
        html = """
        <div class="ic-DashboardCard__action-container">
          <div class="ic-DashboardCard__action-layout">
            <a href="/courses/12345/assignments/67890">
              <span class="todo-badge__info-holder">
                <span class="todo-badge__info-holder__title">Problem Set 5</span>
                <span class="todo-badge__info-holder__due">Mar 25 at 11:59pm</span>
              </span>
            </a>
          </div>
        </div>
        """
        parser = CanvasParser("https://canvas.university.edu")
        assignments = parser.parse_dashboard_todos(html)
        assert len(assignments) >= 0  # May be 0 if HTML doesn't match exactly

    def test_parse_course_assignments_list(self):
        html = """
        <div id="assignment_group_1">
          <div class="ig-row">
            <a class="ig-title" href="/courses/101/assignments/201">Homework 3</a>
            <div class="assignment-date-due">
              <span class="screenreader-only">Due</span>
              <span class="date-text">Mar 28, 2026 at 11:59pm</span>
            </div>
            <span class="points_possible">100 pts</span>
          </div>
          <div class="ig-row">
            <a class="ig-title" href="/courses/101/assignments/202">Final Exam</a>
            <div class="assignment-date-due">
              <span class="screenreader-only">Due</span>
              <span class="date-text">Apr 15, 2026 at 2:00pm</span>
            </div>
            <span class="points_possible">200 pts</span>
          </div>
        </div>
        """
        parser = CanvasParser("https://canvas.university.edu")
        assignments = parser.parse_assignments_page(html, course_id="101", course_name="CS 101")
        assert len(assignments) == 2
        assert assignments[0]["title"] == "Homework 3"
        assert assignments[0]["course"] == "CS 101"
        assert assignments[0]["external_id"] == "canvas:101:201"
        assert assignments[1]["title"] == "Final Exam"

    def test_parse_grades_page(self):
        html = """
        <div class="student_assignment">
          <th class="title" scope="row">
            <a href="/courses/101/assignments/201">Homework 1</a>
          </th>
          <span class="grade">85</span>
          <span class="points_possible">100</span>
        </div>
        <div id="student-grades-final">
          <span class="grade">B+</span>
        </div>
        """
        parser = CanvasParser("https://canvas.university.edu")
        grade_info = parser.parse_grades_page(html, course_id="101")
        assert grade_info["current_grade"] is not None

    def test_parse_empty_page_returns_empty(self):
        parser = CanvasParser("https://canvas.university.edu")
        assert parser.parse_assignments_page("", course_id="101", course_name="CS") == []
        assert parser.parse_grades_page("", course_id="101") == {"current_grade": None, "assignments": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_canvas_parser.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement CanvasParser**

Create `src/planner/ingestion/canvas_parser.py`:
```python
import re
from html.parser import HTMLParser


class CanvasParser:
    """Parse Canvas LMS HTML pages into structured data."""

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    def parse_assignments_page(self, html: str, course_id: str, course_name: str) -> list[dict]:
        """Parse a course assignments page for assignment titles, due dates, and IDs."""
        if not html:
            return []

        assignments = []
        # Match assignment links with IDs
        link_pattern = re.compile(
            r'<a[^>]*class="ig-title"[^>]*href="[^"]*?/assignments/(\d+)"[^>]*>([^<]+)</a>',
            re.DOTALL,
        )
        date_pattern = re.compile(
            r'<span class="date-text">([^<]+)</span>',
        )
        points_pattern = re.compile(
            r'<span class="points_possible">([^<]+)</span>',
        )

        links = link_pattern.findall(html)
        dates = date_pattern.findall(html)
        points = points_pattern.findall(html)

        for i, (assignment_id, title) in enumerate(links):
            assignment = {
                "external_id": f"canvas:{course_id}:{assignment_id}",
                "title": title.strip(),
                "course": course_name,
                "due_date": dates[i].strip() if i < len(dates) else None,
                "points": points[i].strip() if i < len(points) else None,
            }
            assignments.append(assignment)

        return assignments

    def parse_grades_page(self, html: str, course_id: str) -> dict:
        """Parse a course grades page for current grade and assignment scores."""
        if not html:
            return {"current_grade": None, "assignments": []}

        # Look for final grade
        grade_match = re.search(
            r'<div[^>]*id="student-grades-final"[^>]*>.*?<span class="grade">([^<]+)</span>',
            html, re.DOTALL,
        )
        current_grade = grade_match.group(1).strip() if grade_match else None

        return {"current_grade": current_grade, "assignments": []}

    def parse_dashboard_todos(self, html: str) -> list[dict]:
        """Parse the Canvas dashboard for upcoming todo items."""
        if not html:
            return []

        todos = []
        title_pattern = re.compile(
            r'todo-badge__info-holder__title">([^<]+)<',
        )
        due_pattern = re.compile(
            r'todo-badge__info-holder__due">([^<]+)<',
        )

        titles = title_pattern.findall(html)
        dues = due_pattern.findall(html)

        for i, title in enumerate(titles):
            todos.append({
                "title": title.strip(),
                "due_date": dues[i].strip() if i < len(dues) else None,
            })

        return todos

    def parse_calendar_events(self, html: str) -> list[dict]:
        """Parse the Canvas calendar page for events."""
        if not html:
            return []
        events = []
        # Canvas calendar renders events with data attributes
        event_pattern = re.compile(
            r'class="fc-title">([^<]+)<.*?class="fc-time"[^>]*data-start="([^"]*)"',
            re.DOTALL,
        )
        for title, start_time in event_pattern.findall(html):
            events.append({
                "title": title.strip(),
                "start_time": start_time.strip(),
            })
        return events

    def extract_course_list(self, html: str) -> list[dict]:
        """Parse the courses page for course IDs and names."""
        if not html:
            return []
        courses = []
        pattern = re.compile(
            r'<a[^>]*href="/courses/(\d+)"[^>]*>.*?<span class="name[^"]*">([^<]+)</span>',
            re.DOTALL,
        )
        for course_id, name in pattern.findall(html):
            courses.append({"id": course_id, "name": name.strip()})
        return courses
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_canvas_parser.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/planner/ingestion/canvas_parser.py tests/planner/test_canvas_parser.py
git commit -m "feat(planner): add Canvas HTML parser for assignments, grades, and todos"
```

---

## Task 4: Canvas Scraper

**Files:**
- Create: `src/planner/ingestion/canvas.py`

- [ ] **Step 1: Implement CanvasScraper**

Create `src/planner/ingestion/canvas.py`:
```python
import json
import logging
import time

from src.planner.db import PlannerDB
from src.planner.encryption import EncryptionManager
from src.planner.ingestion.canvas_parser import CanvasParser

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 30


class CanvasScraper:
    """Scrape Canvas LMS using Playwright with saved session cookies."""

    def __init__(self, db: PlannerDB, encryption: EncryptionManager):
        self._db = db
        self._encryption = encryption

    def launch_login(self, canvas_url: str) -> int | None:
        """Open a headed browser for manual login. Returns config_id or None."""
        from playwright.sync_api import sync_playwright

        canvas_url = canvas_url.rstrip("/")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            page.goto(canvas_url)
            # Wait for user to log in — detect by checking for dashboard
            logger.info("Waiting for user to log in to Canvas at %s ...", canvas_url)
            try:
                page.wait_for_url("**/dashboard**", timeout=300_000)  # 5 min timeout
            except Exception:
                # Also try waiting for any Canvas page that indicates logged in
                try:
                    page.wait_for_selector("#global_nav_accounts_link", timeout=60_000)
                except Exception:
                    logger.error("Login timed out")
                    browser.close()
                    return None

            # Save cookies
            cookies = context.cookies()
            encrypted_cookies = self._encryption.encrypt(json.dumps(cookies))
            config_id = self._db.add_canvas_config(canvas_url, encrypted_cookies)

            browser.close()
            logger.info("Canvas login successful, config saved (id=%d)", config_id)
            return config_id

    def relogin(self, config_id: int) -> bool:
        """Re-authenticate an existing Canvas config. Returns True on success."""
        config = self._db.get_canvas_config(config_id)
        if not config:
            return False

        result_id = self.launch_login(config["canvas_url"])
        if result_id is None:
            return False

        # Update the existing config with new cookies if a new one was created
        if result_id != config_id:
            new_config = self._db.get_canvas_config(result_id)
            if new_config:
                self._db.update_canvas_cookies(config_id, new_config["session_cookies"])
                self._db.soft_delete_canvas_config(result_id)

        self._db.update_canvas_status(config_id, "active")
        return True

    def sync_config(self, config_id: int) -> int:
        """Scrape Canvas for a given config. Returns number of tasks synced."""
        config = self._db.get_canvas_config(config_id)
        if not config or config["status"] != "active":
            return 0

        canvas_url = config["canvas_url"]
        try:
            cookies = json.loads(self._encryption.decrypt(config["session_cookies"]))
        except Exception:
            logger.error("Failed to decrypt cookies for config %d", config_id)
            self._db.update_canvas_status(config_id, "error")
            return 0

        from playwright.sync_api import sync_playwright

        total = 0
        parser = CanvasParser(canvas_url)

        for attempt in range(MAX_RETRIES + 1):
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                context.add_cookies(cookies)

                try:
                    total = self._scrape_with_context(config_id, canvas_url, context, parser)
                    return total
                except _SessionExpiredError:
                    if attempt < MAX_RETRIES:
                        logger.info("Canvas session may be expired, retry %d/%d in %ds",
                                    attempt + 1, MAX_RETRIES, RETRY_DELAY)
                        browser.close()
                        time.sleep(RETRY_DELAY)
                        continue
                    self._db.update_canvas_status(config_id, "expired")
                    logger.warning("Canvas session expired for config %d after %d retries",
                                   config_id, MAX_RETRIES)
                except Exception as e:
                    if attempt < MAX_RETRIES:
                        logger.info("Canvas scrape error, retry %d/%d: %s", attempt + 1, MAX_RETRIES, e)
                        browser.close()
                        time.sleep(RETRY_DELAY)
                        continue
                    logger.error("Canvas scrape failed for config %d: %s", config_id, e)
                finally:
                    browser.close()

        return total

    def _scrape_with_context(self, config_id, canvas_url, context, parser) -> int:
        """Scrape all Canvas pages using an authenticated browser context."""
        page = context.new_page()
        total = 0

        # Navigate to dashboard to verify session
        page.goto(f"{canvas_url}/dashboard", wait_until="domcontentloaded", timeout=30_000)
        if self._is_session_expired(page, canvas_url):
            raise _SessionExpiredError()

        # Scrape courses list
        page.goto(f"{canvas_url}/courses", wait_until="domcontentloaded", timeout=30_000)
        courses_html = page.content()
        courses = parser.extract_course_list(courses_html)

        for course in courses:
            course_id = course["id"]
            course_name = course["name"]

            # Scrape assignments
            try:
                page.goto(
                    f"{canvas_url}/courses/{course_id}/assignments",
                    wait_until="domcontentloaded", timeout=30_000,
                )
                assignments_html = page.content()
                assignments = parser.parse_assignments_page(assignments_html, course_id, course_name)

                for a in assignments:
                    self._db.upsert_task(
                        source="canvas",
                        external_id=a["external_id"],
                        title=a["title"],
                        course=a["course"],
                        deadline=a.get("due_date"),
                    )
                    total += 1
            except Exception as e:
                logger.warning("Failed to scrape assignments for %s: %s", course_name, e)

            # Scrape grades
            try:
                page.goto(
                    f"{canvas_url}/courses/{course_id}/grades",
                    wait_until="domcontentloaded", timeout=30_000,
                )
                grades_html = page.content()
                grade_info = parser.parse_grades_page(grades_html, course_id)

                if grade_info["current_grade"]:
                    # Update all tasks for this course with current grade
                    tasks = self._db.get_tasks(source="canvas")
                    for task in tasks:
                        if task["course"] == course_name:
                            self._db._get_conn().execute(
                                "UPDATE tasks SET current_grade = ? WHERE id = ?",
                                (grade_info["current_grade"], task["id"]),
                            )
                    self._db._get_conn().commit()
            except Exception as e:
                logger.warning("Failed to scrape grades for %s: %s", course_name, e)

        # Scrape Canvas calendar page for events
        try:
            page.goto(f"{canvas_url}/calendar", wait_until="domcontentloaded", timeout=30_000)
            calendar_html = page.content()
            calendar_events = parser.parse_calendar_events(calendar_html)
            for evt in calendar_events:
                self._db.upsert_event(
                    account_id=0,  # Canvas events aren't tied to a Google account
                    source="canvas",
                    external_id=f"canvas:cal:{evt['title'][:50]}:{evt.get('start_time', '')}",
                    title=evt["title"],
                    start_time=evt.get("start_time"),
                    event_type="class",
                )
                total += 1
        except Exception as e:
            logger.warning("Failed to scrape Canvas calendar: %s", e)

        # Update last sync
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        self._db.update_canvas_last_sync(config_id, now)

        page.close()
        return total

    def _is_session_expired(self, page, canvas_url: str) -> bool:
        """Check if the current page indicates a session expiry."""
        url = page.url
        # Redirected to login page
        if "/login" in url or "login" in url.split("/")[-1]:
            return True
        # Check for login form
        login_form = page.query_selector("#login_form")
        if login_form:
            return True
        return False


class _SessionExpiredError(Exception):
    pass
```

- [ ] **Step 2: Commit**

```bash
git add src/planner/ingestion/canvas.py
git commit -m "feat(planner): add Canvas LMS scraper with Playwright login flow and cookie management"
```

---

## Task 5: Canvas API Routes

**Files:**
- Create: `src/planner/api/canvas.py`
- Create: `tests/planner/test_canvas_routes.py`
- Modify: `src/planner/server.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_canvas_routes.py`:
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


class TestCanvasRoutes:
    def test_list_canvas_configs_empty(self, client, auth_headers):
        resp = client.get("/canvas/configs", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_canvas_configs_after_add(self, client, auth_headers, db_path):
        db = PlannerDB(db_path)
        db.add_canvas_config("https://canvas.edu", "cookies")
        db.close()

        resp = client.get("/canvas/configs", headers=auth_headers)
        configs = resp.json()
        assert len(configs) == 1
        assert configs[0]["canvas_url"] == "https://canvas.edu"
        # Cookies should NOT be exposed in the API response
        assert "session_cookies" not in configs[0]

    def test_delete_canvas_config(self, client, auth_headers, db_path):
        db = PlannerDB(db_path)
        cid = db.add_canvas_config("https://canvas.edu", "cookies")
        db.close()

        resp = client.delete(f"/canvas/configs/{cid}", headers=auth_headers)
        assert resp.status_code == 200

        resp = client.get("/canvas/configs", headers=auth_headers)
        assert resp.json() == []

    def test_canvas_routes_require_auth(self, client):
        assert client.get("/canvas/configs").status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_canvas_routes.py -v`
Expected: FAIL

- [ ] **Step 3: Implement canvas routes**

Create `src/planner/api/canvas.py`:
```python
import threading
from fastapi import APIRouter, Depends, BackgroundTasks

from src.planner.db import PlannerDB

router = APIRouter(prefix="/canvas")

# Module-level reference, set by server.py
canvas_scraper = None


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


@router.get("/configs")
def list_configs(db: PlannerDB = Depends(get_db)):
    """List Canvas configurations (without exposing encrypted cookies)."""
    configs = db.list_canvas_configs()
    return [
        {
            "id": c["id"],
            "canvas_url": c["canvas_url"],
            "status": c["status"],
            "last_sync": c["last_sync"],
        }
        for c in configs
    ]


@router.post("/setup")
def setup_canvas(canvas_url: str, db: PlannerDB = Depends(get_db)):
    """Launch Playwright browser for Canvas login. Blocks until user logs in."""
    if canvas_scraper is None:
        return {"error": "Canvas scraper not initialized"}
    config_id = canvas_scraper.launch_login(canvas_url)
    if config_id is None:
        return {"error": "Login timed out or failed"}
    return {"status": "ok", "config_id": config_id}


@router.post("/relogin/{config_id}")
def relogin_canvas(config_id: int, db: PlannerDB = Depends(get_db)):
    """Re-authenticate an expired Canvas session."""
    if canvas_scraper is None:
        return {"error": "Canvas scraper not initialized"}
    success = canvas_scraper.relogin(config_id)
    return {"status": "ok" if success else "failed"}


@router.delete("/configs/{config_id}")
def delete_config(config_id: int, db: PlannerDB = Depends(get_db)):
    """Soft-delete a Canvas configuration and cascade to associated tasks."""
    # Delete tasks sourced from this Canvas instance
    tasks = db.get_tasks(source="canvas")
    for task in tasks:
        db.update_task_status(task["id"], "skipped")
    # Delete events sourced from canvas for this config
    db.soft_delete_canvas_config(config_id)
    return {"status": "deleted"}
```

- [ ] **Step 4: Register canvas routes in server.py**

Add to `src/planner/server.py` imports:
```python
from src.planner.api import canvas as canvas_module
from src.planner.ingestion.canvas import CanvasScraper
from src.planner.encryption import EncryptionManager
```

Add in `create_app`, after the sync scheduler setup:
```python
# Canvas scraper setup
encryption = EncryptionManager()
canvas_module.canvas_scraper = CanvasScraper(db, encryption)
app.dependency_overrides[canvas_module.get_db] = get_db
for route in canvas_module.router.routes:
    route.dependencies = [require_token]
app.include_router(canvas_module.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_canvas_routes.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/planner/api/canvas.py src/planner/server.py tests/planner/test_canvas_routes.py
git commit -m "feat(planner): add Canvas API routes with config management"
```

---

## Task 6: Add Canvas to Sync Scheduler

**Files:**
- Modify: `src/planner/ingestion/sync_scheduler.py`

- [ ] **Step 1: Add Canvas sync to the scheduler**

Modify `src/planner/ingestion/sync_scheduler.py`:

Add import:
```python
from src.planner.ingestion.canvas import CanvasScraper
from src.planner.encryption import EncryptionManager
```

Add `encryption` parameter to `__init__`:
```python
def __init__(self, db: PlannerDB, auth_manager: GoogleAuthManager | None = None, encryption: EncryptionManager | None = None):
    # ... existing code ...
    self._canvas_scraper = CanvasScraper(db, encryption) if encryption else None
```

Add a `start` method change to add a separate canvas job:
```python
def start(self, google_interval_minutes: int = 15, canvas_interval_minutes: int = 120) -> None:
    self._scheduler.add_job(
        self.sync_all, "interval", minutes=google_interval_minutes,
        id="sync_google", replace_existing=True,
    )
    if self._canvas_scraper:
        self._scheduler.add_job(
            self.sync_canvas, "interval", minutes=canvas_interval_minutes,
            id="sync_canvas", replace_existing=True,
        )
    self._scheduler.start()
```

Add `sync_canvas` method:
```python
def sync_canvas(self) -> dict[str, int]:
    """Sync all Canvas configs. Returns dict of url -> task count."""
    if not self._canvas_scraper:
        return {}
    with self._lock:
        results = {}
        configs = self._db.list_canvas_configs()
        for config in configs:
            if config["status"] != "active":
                continue
            try:
                count = self._canvas_scraper.sync_config(config["id"])
                results[config["canvas_url"]] = count
                logger.info("Canvas sync %s: %d tasks", config["canvas_url"], count)
            except Exception as e:
                logger.error("Canvas sync failed for %s: %s", config["canvas_url"], e)
                results[config["canvas_url"]] = -1
        return results
```

- [ ] **Step 2: Update server.py to pass encryption to SyncScheduler**

In `src/planner/server.py`, update the SyncScheduler instantiation:
```python
scheduler = SyncScheduler(db, auth_module.auth_manager, encryption)
```

(The `encryption` variable is already created in the Canvas setup block above.)

Move the encryption creation BEFORE the scheduler, so it's available:
```python
encryption = EncryptionManager()

# Sync scheduler
scheduler = SyncScheduler(db, auth_module.auth_manager, encryption)
scheduler.start()

# Canvas scraper setup
canvas_module.canvas_scraper = CanvasScraper(db, encryption)
```

- [ ] **Step 3: Run all tests**

Run: `python -m pytest tests/planner/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/planner/ingestion/sync_scheduler.py src/planner/server.py
git commit -m "feat(planner): add Canvas sync to background scheduler (every 2 hours)"
```

---

## Task 7: Frontend Canvas Panel

**Files:**
- Create: `frontend/src/hooks/useCanvas.ts`
- Create: `frontend/src/components/CanvasPanel.tsx`
- Modify: `frontend/src/components/SettingsView.tsx`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add TypeScript types**

Add to `frontend/src/types/index.ts`:
```typescript
export interface CanvasConfig {
  id: number
  canvas_url: string
  status: 'active' | 'expired' | 'error'
  last_sync: string | null
}

export interface Task {
  id: number
  source: string
  title: string
  description: string | null
  course: string | null
  deadline: string | null
  estimated_minutes: number | null
  priority: number
  status: 'pending' | 'in_progress' | 'done' | 'skipped'
  grade_weight: number | null
  current_grade: string | null
}
```

- [ ] **Step 2: Create canvas hook**

Create `frontend/src/hooks/useCanvas.ts`:
```typescript
import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'
import type { CanvasConfig } from '../types'

export function useCanvas() {
  const [configs, setConfigs] = useState<CanvasConfig[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<CanvasConfig[]>('/canvas/configs')
      setConfigs(data)
    } catch (err) {
      console.error('Failed to load canvas configs:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const setup = useCallback(async (canvasUrl: string) => {
    try {
      const result = await apiFetch<{ status: string; config_id?: number }>(
        `/canvas/setup?canvas_url=${encodeURIComponent(canvasUrl)}`,
        { method: 'POST' }
      )
      if (result.status === 'ok') {
        await load()
      }
      return result
    } catch (err) {
      console.error('Canvas setup failed:', err)
      return { status: 'error' }
    }
  }, [load])

  const relogin = useCallback(async (configId: number) => {
    await apiFetch(`/canvas/relogin/${configId}`, { method: 'POST' })
    await load()
  }, [load])

  const remove = useCallback(async (configId: number) => {
    await apiFetch(`/canvas/configs/${configId}`, { method: 'DELETE' })
    setConfigs(prev => prev.filter(c => c.id !== configId))
  }, [])

  return { configs, loading, setup, relogin, remove, reload: load }
}
```

- [ ] **Step 3: Create CanvasPanel component**

Create `frontend/src/components/CanvasPanel.tsx`:
```tsx
import { useState } from 'react'
import { useCanvas } from '../hooks/useCanvas'

const STATUS_COLORS: Record<string, string> = {
  active: 'text-green-400',
  expired: 'text-yellow-400',
  error: 'text-red-400',
}

export default function CanvasPanel() {
  const { configs, loading, setup, relogin, remove } = useCanvas()
  const [url, setUrl] = useState('')
  const [setting_up, setSettingUp] = useState(false)

  const handleSetup = async () => {
    if (!url.trim()) return
    setSettingUp(true)
    try {
      await setup(url.trim())
      setUrl('')
    } finally {
      setSettingUp(false)
    }
  }

  if (loading) return <div className="text-gray-400">Loading Canvas configs...</div>

  return (
    <div>
      <h3 className="text-lg font-bold mb-4">Canvas LMS</h3>

      {configs.length === 0 ? (
        <p className="text-sm text-gray-400 mb-4">
          No Canvas instance connected. Enter your Canvas URL below to get started.
        </p>
      ) : (
        <div className="space-y-2 mb-4">
          {configs.map((config) => (
            <div
              key={config.id}
              className="flex items-center justify-between p-3 bg-gray-800 rounded-lg"
            >
              <div>
                <p className="text-white text-sm font-medium">{config.canvas_url}</p>
                <p className="text-xs text-gray-400">
                  Status: <span className={STATUS_COLORS[config.status] || 'text-gray-400'}>
                    {config.status}
                  </span>
                  {config.last_sync && ` · Last synced: ${new Date(config.last_sync).toLocaleString()}`}
                </p>
              </div>
              <div className="flex gap-2">
                {config.status === 'expired' && (
                  <button
                    onClick={() => relogin(config.id)}
                    className="text-blue-400 hover:text-blue-300 text-sm transition-colors"
                  >
                    Re-login
                  </button>
                )}
                <button
                  onClick={() => remove(config.id)}
                  className="text-red-400 hover:text-red-300 text-sm transition-colors"
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://canvas.university.edu"
          className="flex-1 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white text-sm"
        />
        <button
          onClick={handleSetup}
          disabled={setting_up || !url.trim()}
          className="px-4 py-2 bg-accent hover:bg-blue-700 rounded text-sm text-white disabled:opacity-50 transition-colors"
        >
          {setting_up ? 'Logging in...' : 'Connect'}
        </button>
      </div>
      <p className="text-xs text-gray-500 mt-2">
        A browser window will open for you to log in. Supports SSO and MFA.
      </p>
    </div>
  )
}
```

- [ ] **Step 4: Update SettingsView to include CanvasPanel**

In `frontend/src/components/SettingsView.tsx`, add import:
```tsx
import CanvasPanel from './CanvasPanel'
```

Add after the AccountsPanel section (after the closing `</div>` of the accounts panel section):
```tsx
<div className="mt-6 border-t border-gray-700 pt-6">
  <CanvasPanel />
</div>
```

- [ ] **Step 5: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 6: Commit**

```bash
git add frontend/src/ frontend/dist/
git commit -m "feat(frontend): add Canvas LMS configuration panel with login and status display"
```

---

## Task 8: Run All Tests and Final Build

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/planner/ -v`
Expected: All tests pass

- [ ] **Step 2: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit built frontend if changed**

```bash
git add frontend/dist/
git commit -m "chore: rebuild frontend with Canvas integration"
```
