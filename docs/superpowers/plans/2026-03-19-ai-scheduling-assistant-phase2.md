# AI Scheduling Assistant — Phase 2: Google Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect multiple Google accounts via OAuth 2.0, sync Gmail and Google Calendar data, extract events and action items, and display them on the planner calendar.

**Architecture:** A Google OAuth 2.0 flow (with CSRF `state` parameter) authenticates users via browser redirect to `localhost:8321/auth/callback`. Tokens are stored in the OS credential store via `keyring`. A Gmail syncer scans inbox/starred for action items and deadlines. A Google Calendar syncer pulls events from all calendars. Both sync every 15 minutes via a background scheduler. Synced data is stored in the existing SQLite database and served via new API endpoints. The React frontend gets an accounts management UI and calendar event rendering.

**Tech Stack:** `google-auth-oauthlib`, `google-api-python-client`, `keyring`, `APScheduler`, FastAPI, React/FullCalendar

**Spec:** `docs/superpowers/specs/2026-03-19-ai-scheduling-assistant-design.md` (Sections 3.1, 3.2, 7, 8)

**Depends on:** Phase 1 (FastAPI server, SQLite DB, React shell, encryption helpers)

---

## File Structure

### New Python Files

| File | Responsibility |
|------|---------------|
| `src/planner/ingestion/__init__.py` | Package init |
| `src/planner/ingestion/google_auth.py` | OAuth 2.0 flow: generate auth URL, handle callback, store/retrieve tokens via keyring, refresh tokens |
| `src/planner/ingestion/gmail.py` | Gmail API client: fetch recent emails, extract action items/deadlines, sync to DB |
| `src/planner/ingestion/gcal.py` | Google Calendar API client: fetch events from all calendars, sync to DB with dedup |
| `src/planner/ingestion/sync_scheduler.py` | APScheduler background jobs: periodic Gmail + GCal sync every 15 min |
| `src/planner/api/auth.py` | OAuth routes: GET /auth/google, GET /auth/callback, GET /auth/accounts, DELETE /auth/accounts/:id |
| `src/planner/api/events.py` | Events route: GET /api/events (filterable by date range, source) |
| `src/planner/api/sync.py` | Sync routes: POST /sync/trigger, GET /sync/status |

### Modified Python Files

| File | Change |
|------|--------|
| `src/planner/db.py` | Add account CRUD, event CRUD, sync state tracking methods |
| `src/planner/server.py` | Register new routers (auth, events, sync), init sync scheduler |
| `requirements.txt` | Add google-auth-oauthlib, google-api-python-client, APScheduler |

### New Frontend Files

| File | Responsibility |
|------|---------------|
| `frontend/src/components/AccountsPanel.tsx` | List connected accounts, add/remove buttons |
| `frontend/src/hooks/useAccounts.ts` | Account data fetching + mutations |
| `frontend/src/hooks/useEvents.ts` | Events data fetching for calendar rendering |

### Modified Frontend Files

| File | Change |
|------|--------|
| `frontend/src/components/SettingsView.tsx` | Add AccountsPanel integration |
| `frontend/src/components/CalendarView.tsx` | Render synced events from API |
| `frontend/src/types/index.ts` | Add Account, CalendarEvent interfaces |

### Test Files

| File | Tests |
|------|-------|
| `tests/planner/test_google_auth.py` | OAuth URL generation, callback handling, token storage/retrieval, refresh |
| `tests/planner/test_gmail.py` | Email fetching, action item extraction, sync to DB |
| `tests/planner/test_gcal.py` | Calendar event fetching, dedup, sync to DB |
| `tests/planner/test_auth_routes.py` | Auth API endpoints |
| `tests/planner/test_events_routes.py` | Events API endpoint filtering |
| `tests/planner/test_sync_routes.py` | Sync trigger and status endpoints |
| `tests/planner/test_db_accounts.py` | Account and event CRUD on DB |

---

## Task 1: Add Dependencies

**Files:**
- Modify: `requirements.txt`
- Modify: `frontend/package.json` (no changes needed — no new frontend deps)

- [ ] **Step 1: Add Python dependencies**

Append to `requirements.txt`:
```
google-auth-oauthlib>=1.2.0
google-api-python-client>=2.140.0
APScheduler>=3.10.4
```

- [ ] **Step 2: Install**

Run: `pip install -r requirements.txt`
Expected: All packages install successfully

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add Google API and APScheduler dependencies for Phase 2"
```

---

## Task 2: Database Account and Event CRUD

**Files:**
- Modify: `src/planner/db.py`
- Create: `tests/planner/test_db_accounts.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_db_accounts.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_db_accounts.py -v`
Expected: FAIL — `AttributeError: 'PlannerDB' object has no attribute 'add_account'`

- [ ] **Step 3: Implement account and event CRUD methods**

Add these methods to `src/planner/db.py` in the `PlannerDB` class:

```python
# --- Account CRUD ---

def add_account(self, email: str, provider: str = "google", scopes: str = "") -> int:
    conn = self._get_conn()
    # Return existing if duplicate
    cursor = conn.execute(
        "SELECT id FROM accounts WHERE email = ? AND deleted_at IS NULL", (email,)
    )
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor = conn.execute(
        "INSERT INTO accounts (email, provider, scopes) VALUES (?, ?, ?)",
        (email, provider, scopes),
    )
    conn.commit()
    return cursor.lastrowid

def get_account(self, account_id: int) -> dict | None:
    conn = self._get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
    row = cursor.fetchone()
    conn.row_factory = None
    return dict(row) if row else None

def list_accounts(self) -> list[dict]:
    conn = self._get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM accounts WHERE deleted_at IS NULL ORDER BY email"
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.row_factory = None
    return rows

def soft_delete_account(self, account_id: int) -> None:
    conn = self._get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE accounts SET deleted_at = ? WHERE id = ?", (now, account_id)
    )
    conn.commit()

def update_account_last_sync(self, account_id: int, timestamp: str) -> None:
    conn = self._get_conn()
    conn.execute(
        "UPDATE accounts SET last_sync = ? WHERE id = ?", (timestamp, account_id)
    )
    conn.commit()

# --- Event CRUD ---

def upsert_event(
    self,
    account_id: int,
    source: str,
    external_id: str,
    title: str,
    start_time: str | None = None,
    end_time: str | None = None,
    all_day: bool = False,
    description: str | None = None,
    location: str | None = None,
    event_type: str | None = None,
    recurring_rule: str | None = None,
    raw_data: str | None = None,
) -> int:
    conn = self._get_conn()
    now = datetime.now(timezone.utc).isoformat()
    # Check for existing
    cursor = conn.execute(
        "SELECT id FROM events WHERE source = ? AND external_id = ?",
        (source, external_id),
    )
    row = cursor.fetchone()
    if row:
        conn.execute(
            """UPDATE events SET title=?, description=?, start_time=?, end_time=?,
               all_day=?, location=?, event_type=?, recurring_rule=?, raw_data=?, synced_at=?
               WHERE id=?""",
            (title, description, start_time, end_time, int(all_day),
             location, event_type, recurring_rule, raw_data, now, row[0]),
        )
        conn.commit()
        return row[0]
    cursor = conn.execute(
        """INSERT INTO events (account_id, source, external_id, title, description,
           start_time, end_time, all_day, location, event_type, recurring_rule, raw_data, synced_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (account_id, source, external_id, title, description, start_time, end_time,
         int(all_day), location, event_type, recurring_rule, raw_data, now),
    )
    conn.commit()
    return cursor.lastrowid

def get_events(
    self,
    source: str | None = None,
    start_after: str | None = None,
    end_before: str | None = None,
) -> list[dict]:
    conn = self._get_conn()
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM events WHERE 1=1"
    params: list = []
    if source:
        query += " AND source = ?"
        params.append(source)
    if start_after:
        query += " AND start_time >= ?"
        params.append(start_after)
    if end_before:
        query += " AND start_time < ?"
        params.append(end_before)
    query += " ORDER BY start_time"
    cursor = conn.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.row_factory = None
    return rows

def delete_events_for_account(self, account_id: int) -> None:
    conn = self._get_conn()
    conn.execute("DELETE FROM events WHERE account_id = ?", (account_id,))
    conn.commit()
```

Also add this import at the top of `db.py`:
```python
from datetime import datetime, timezone
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_db_accounts.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/planner/db.py tests/planner/test_db_accounts.py
git commit -m "feat(planner): add account and event CRUD methods to database layer"
```

---

## Task 3: Google OAuth 2.0 Flow

**Files:**
- Create: `src/planner/ingestion/__init__.py`
- Create: `src/planner/ingestion/google_auth.py`
- Create: `tests/planner/test_google_auth.py`

- [ ] **Step 1: Create package init**

Create `src/planner/ingestion/__init__.py` (empty file).

- [ ] **Step 2: Write failing tests**

Create `tests/planner/test_google_auth.py`:
```python
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.planner.ingestion.google_auth import GoogleAuthManager


FAKE_CLIENT_CONFIG = {
    "web": {
        "client_id": "fake-client-id.apps.googleusercontent.com",
        "client_secret": "fake-secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8321/auth/callback"],
    }
}


@pytest.fixture
def auth_manager():
    with patch("src.planner.ingestion.google_auth.keyring") as mock_kr:
        mock_kr.get_password.return_value = None
        mgr = GoogleAuthManager(
            client_config=FAKE_CLIENT_CONFIG,
            redirect_uri="http://localhost:8321/auth/callback",
            scopes=["https://www.googleapis.com/auth/gmail.readonly",
                     "https://www.googleapis.com/auth/calendar.readonly"],
        )
        yield mgr, mock_kr


class TestGoogleAuthManager:
    def test_generate_auth_url_returns_url_and_state(self, auth_manager):
        mgr, _ = auth_manager
        url, state = mgr.generate_auth_url()
        assert "accounts.google.com" in url
        assert "state=" in url
        assert len(state) > 10

    def test_generate_auth_url_includes_scopes(self, auth_manager):
        mgr, _ = auth_manager
        url, _ = mgr.generate_auth_url()
        assert "gmail.readonly" in url
        assert "calendar.readonly" in url

    def test_store_tokens_uses_keyring(self, auth_manager):
        mgr, mock_kr = auth_manager
        mgr.store_tokens("user@gmail.com", {
            "token": "access-token-123",
            "refresh_token": "refresh-token-456",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "fake-client-id",
            "client_secret": "fake-secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        })
        mock_kr.set_password.assert_called_once()
        call_args = mock_kr.set_password.call_args[0]
        assert call_args[0] == "productivity-planner"
        assert call_args[1] == "user@gmail.com"
        stored = json.loads(call_args[2])
        assert stored["token"] == "access-token-123"
        assert stored["refresh_token"] == "refresh-token-456"

    def test_get_credentials_returns_none_when_no_tokens(self, auth_manager):
        mgr, mock_kr = auth_manager
        mock_kr.get_password.return_value = None
        creds = mgr.get_credentials("user@gmail.com")
        assert creds is None

    def test_get_credentials_returns_credentials_when_stored(self, auth_manager):
        mgr, mock_kr = auth_manager
        mock_kr.get_password.return_value = json.dumps({
            "token": "access-token",
            "refresh_token": "refresh-token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "fake-client-id",
            "client_secret": "fake-secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        })
        creds = mgr.get_credentials("user@gmail.com")
        assert creds is not None
        assert creds.token == "access-token"

    def test_remove_tokens(self, auth_manager):
        mgr, mock_kr = auth_manager
        mgr.remove_tokens("user@gmail.com")
        mock_kr.delete_password.assert_called_once_with(
            "productivity-planner", "user@gmail.com"
        )
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_google_auth.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement GoogleAuthManager**

Create `src/planner/ingestion/google_auth.py`:
```python
import json
import secrets
from typing import Any

import keyring
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

KEYRING_SERVICE = "productivity-planner"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]


class GoogleAuthManager:
    def __init__(
        self,
        client_config: dict[str, Any],
        redirect_uri: str = "http://localhost:8321/auth/callback",
        scopes: list[str] | None = None,
    ):
        self._client_config = client_config
        self._redirect_uri = redirect_uri
        self._scopes = scopes or SCOPES
        self._pending_states: dict[str, Flow] = {}

    def generate_auth_url(self) -> tuple[str, str]:
        """Generate OAuth authorization URL with CSRF state parameter."""
        flow = Flow.from_client_config(
            self._client_config,
            scopes=self._scopes,
            redirect_uri=self._redirect_uri,
        )
        state = secrets.token_urlsafe(32)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        self._pending_states[state] = flow
        return auth_url, state

    def handle_callback(self, code: str, state: str) -> tuple[Credentials, str]:
        """Exchange authorization code for credentials. Returns (credentials, email)."""
        flow = self._pending_states.pop(state, None)
        if flow is None:
            raise ValueError("Invalid or expired OAuth state parameter")
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Get user email from the ID token or userinfo
        from googleapiclient.discovery import build
        service = build("oauth2", "v2", credentials=credentials)
        user_info = service.userinfo().get().execute()
        email = user_info["email"]

        return credentials, email

    def store_tokens(self, email: str, token_data: dict) -> None:
        """Store OAuth tokens in OS credential store."""
        keyring.set_password(
            KEYRING_SERVICE, email, json.dumps(token_data)
        )

    def get_credentials(self, email: str) -> Credentials | None:
        """Retrieve credentials from OS credential store."""
        stored = keyring.get_password(KEYRING_SERVICE, email)
        if not stored:
            return None
        data = json.loads(stored)
        return Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            scopes=data.get("scopes"),
        )

    def refresh_if_expired(self, email: str) -> Credentials | None:
        """Get credentials, refreshing if expired."""
        creds = self.get_credentials(email)
        if creds is None:
            return None
        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            self.store_tokens(email, {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": list(creds.scopes) if creds.scopes else [],
            })
        return creds

    def remove_tokens(self, email: str) -> None:
        """Remove stored tokens from OS credential store."""
        keyring.delete_password(KEYRING_SERVICE, email)

    def credentials_to_dict(self, creds: Credentials) -> dict:
        """Serialize credentials for storage."""
        return {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes) if creds.scopes else [],
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_google_auth.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/planner/ingestion/__init__.py src/planner/ingestion/google_auth.py tests/planner/test_google_auth.py
git commit -m "feat(planner): add Google OAuth 2.0 auth manager with keyring token storage"
```

---

## Task 4: Google Calendar Syncer

**Files:**
- Create: `src/planner/ingestion/gcal.py`
- Create: `tests/planner/test_gcal.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_gcal.py`:
```python
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

        # Update title and resync
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_gcal.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement GCalSyncer**

Create `src/planner/ingestion/gcal.py`:
```python
import json
from datetime import datetime, timezone

from src.planner.db import PlannerDB


class GCalSyncer:
    def __init__(self, db: PlannerDB):
        self._db = db

    def sync_account(self, account_id: int, service) -> int:
        """Sync all calendars for an account. Returns number of events synced."""
        calendars = service.calendarList().list().execute()
        total = 0

        for cal in calendars.get("items", []):
            cal_id = cal["id"]
            total += self._sync_calendar(account_id, service, cal_id)

        now = datetime.now(timezone.utc).isoformat()
        self._db.update_account_last_sync(account_id, now)
        return total

    def _sync_calendar(self, account_id: int, service, calendar_id: str) -> int:
        """Sync a single calendar. Returns count of events."""
        from datetime import timedelta
        count = 0
        page_token = None
        # Only fetch events from 7 days ago onwards (avoid pulling entire history)
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
                self._upsert_event(account_id, calendar_id, item)
                count += 1

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return count

    def _upsert_event(self, account_id: int, calendar_id: str, item: dict) -> None:
        """Insert or update a single calendar event."""
        event_id = item.get("id", "")
        external_id = f"gcal:{calendar_id}:{event_id}"

        start = item.get("start", {})
        end = item.get("end", {})

        is_all_day = "date" in start
        start_time = start.get("date") or start.get("dateTime")
        end_time = end.get("date") or end.get("dateTime")

        self._db.upsert_event(
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_gcal.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/planner/ingestion/gcal.py tests/planner/test_gcal.py
git commit -m "feat(planner): add Google Calendar syncer with multi-calendar and dedup support"
```

---

## Task 5: Gmail Syncer

**Files:**
- Create: `src/planner/ingestion/gmail.py`
- Create: `tests/planner/test_gmail.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_gmail.py`:
```python
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
    """Create a mock Gmail message."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_gmail.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement GmailSyncer**

Create `src/planner/ingestion/gmail.py`:
```python
import base64
from datetime import datetime, timezone

from src.planner.db import PlannerDB


class GmailSyncer:
    def __init__(self, db: PlannerDB):
        self._db = db

    def fetch_recent_messages(self, service, max_results: int = 50) -> list[dict]:
        """Fetch recent inbox and starred messages, skipping promotions/spam."""
        # Fetch from inbox (excluding promotions/social/spam)
        inbox_results = service.users().messages().list(
            userId="me",
            maxResults=max_results,
            q="-category:promotions -category:social -in:spam in:inbox",
        ).execute()

        # Also fetch starred messages (may not be in inbox)
        starred_results = service.users().messages().list(
            userId="me",
            maxResults=max_results,
            q="is:starred",
        ).execute()

        # Merge and dedup by message ID
        seen_ids = set()
        msg_stubs = []
        for result in [inbox_results, starred_results]:
            for stub in result.get("messages", []):
                if stub["id"] not in seen_ids:
                    seen_ids.add(stub["id"])
                    msg_stubs.append(stub)

        messages = []
        for msg_stub in msg_stubs[:max_results]:
            msg = service.users().messages().get(
                userId="me", id=msg_stub["id"], format="full"
            ).execute()
            messages.append(msg)

        return messages

    def extract_metadata(self, message: dict) -> dict:
        """Extract useful metadata from a Gmail message."""
        headers = message.get("payload", {}).get("headers", [])
        header_map = {h["name"].lower(): h["value"] for h in headers}

        body = ""
        payload = message.get("payload", {})
        if payload.get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        elif payload.get("parts"):
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break

        return {
            "message_id": message.get("id", ""),
            "subject": header_map.get("subject", "(No subject)"),
            "from": header_map.get("from", ""),
            "date": header_map.get("date", ""),
            "body": body,
            "snippet": message.get("snippet", ""),
            "label_ids": message.get("labelIds", []),
        }

    def store_email_event(
        self,
        account_id: int,
        message_id: str,
        subject: str,
        date_str: str,
        snippet: str = "",
    ) -> int:
        """Store an email-derived event in the database."""
        return self._db.upsert_event(
            account_id=account_id,
            source="gmail",
            external_id=f"gmail:{message_id}",
            title=subject,
            description=snippet,
            start_time=date_str,
            event_type="email",
        )

    def sync_account(self, account_id: int, service) -> int:
        """Fetch and store recent emails as raw events. Returns count stored.

        Note: In Phase 2, emails are stored as-is with subject/snippet metadata.
        Claude-based action item extraction (parsing emails for deadlines, tasks,
        and date references) is implemented in Phase 4 (AI Scheduling Engine),
        which processes these stored emails to create tasks.
        """
        messages = self.fetch_recent_messages(service)
        count = 0
        for msg in messages:
            meta = self.extract_metadata(msg)
            self.store_email_event(
                account_id=account_id,
                message_id=meta["message_id"],
                subject=meta["subject"],
                date_str=meta["date"],
                snippet=meta["snippet"],
            )
            count += 1

        now = datetime.now(timezone.utc).isoformat()
        self._db.update_account_last_sync(account_id, now)
        return count
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_gmail.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/planner/ingestion/gmail.py tests/planner/test_gmail.py
git commit -m "feat(planner): add Gmail syncer with metadata extraction and inbox filtering"
```

---

## Task 6: Auth API Routes

**Files:**
- Create: `src/planner/api/auth.py`
- Create: `tests/planner/test_auth_routes.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_auth_routes.py`:
```python
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.planner.server import create_app


FAKE_CLIENT_CONFIG = {
    "web": {
        "client_id": "fake.apps.googleusercontent.com",
        "client_secret": "fake-secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8321/auth/callback"],
    }
}


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
    app = create_app(
        db_path=db_path,
        auth_token=token,
        google_client_config=FAKE_CLIENT_CONFIG,
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


class TestAuthRoutes:
    def test_get_auth_google_returns_redirect_url(self, client, auth_headers):
        resp = client.get("/auth/google", headers=auth_headers, follow_redirects=False)
        assert resp.status_code == 200
        data = resp.json()
        assert "auth_url" in data
        assert "accounts.google.com" in data["auth_url"]

    def test_list_accounts_empty(self, client, auth_headers):
        resp = client.get("/auth/accounts", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_accounts_after_add(self, client, auth_headers, db_path):
        # Manually add an account to DB
        from src.planner.db import PlannerDB
        db = PlannerDB(db_path)
        db.add_account("test@gmail.com", "google", "gmail.readonly")
        db.close()

        resp = client.get("/auth/accounts", headers=auth_headers)
        assert resp.status_code == 200
        accounts = resp.json()
        assert len(accounts) == 1
        assert accounts[0]["email"] == "test@gmail.com"

    def test_delete_account(self, client, auth_headers, db_path):
        from src.planner.db import PlannerDB
        db = PlannerDB(db_path)
        aid = db.add_account("test@gmail.com", "google", "gmail.readonly")
        db.close()

        with patch("src.planner.api.auth.auth_manager") as mock_auth:
            resp = client.delete(f"/auth/accounts/{aid}", headers=auth_headers)
            assert resp.status_code == 200

        resp = client.get("/auth/accounts", headers=auth_headers)
        assert resp.json() == []

    def test_auth_routes_require_auth(self, client):
        assert client.get("/auth/accounts").status_code == 401
        assert client.get("/auth/google").status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_auth_routes.py -v`
Expected: FAIL

- [ ] **Step 3: Implement auth routes**

Create `src/planner/api/auth.py`:

**Design decision:** The `/auth/callback` endpoint must be unauthenticated because Google redirects the browser there (no bearer token). All other auth routes require the bearer token. We use two separate routers: `router` (protected) and `callback_router` (unprotected).

```python
from fastapi import APIRouter, Depends

from src.planner.db import PlannerDB
from src.planner.ingestion.google_auth import GoogleAuthManager

# Protected routes (bearer token required — applied by server.py)
router = APIRouter(prefix="/auth")

# Unprotected route (Google redirects browser here)
callback_router = APIRouter(prefix="/auth")

# Module-level reference, set by server.py
auth_manager: GoogleAuthManager | None = None


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


@router.get("/google")
def initiate_google_auth(db: PlannerDB = Depends(get_db)):
    """Generate OAuth URL and return it. Frontend opens it in browser."""
    if auth_manager is None:
        return {"error": "Google OAuth not configured. Set client config in settings."}
    auth_url, state = auth_manager.generate_auth_url()
    return {"auth_url": auth_url, "state": state}


@callback_router.get("/callback")
def oauth_callback(code: str, state: str, db: PlannerDB = Depends(get_db)):
    """Handle OAuth redirect with authorization code. Unauthenticated — Google redirects here."""
    if auth_manager is None:
        return {"error": "Google OAuth not configured"}
    try:
        credentials, email = auth_manager.handle_callback(code, state)
        auth_manager.store_tokens(email, auth_manager.credentials_to_dict(credentials))
        scopes = " ".join(credentials.scopes) if credentials.scopes else ""
        db.add_account(email, "google", scopes)
        return {"status": "ok", "email": email, "message": "Account connected. You can close this tab."}
    except ValueError as e:
        return {"error": str(e)}


@router.get("/accounts")
def list_accounts(db: PlannerDB = Depends(get_db)):
    """List all connected Google accounts."""
    return db.list_accounts()


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, db: PlannerDB = Depends(get_db)):
    """Soft-delete an account and remove tokens from keyring."""
    account = db.get_account(account_id)
    if account and auth_manager:
        try:
            auth_manager.remove_tokens(account["email"])
        except Exception:
            pass
    db.delete_events_for_account(account_id)
    db.soft_delete_account(account_id)
    return {"status": "deleted"}
```

- [ ] **Step 4: Update server.py to register auth routes**

In `src/planner/server.py`, modify `create_app`:

Add imports:
```python
from src.planner.api import auth as auth_module
from src.planner.ingestion.google_auth import GoogleAuthManager
```

Add to `create_app` signature: `google_client_config: dict | None = None,`

Add in the body (after DB init, before router registration):
```python
# Google OAuth setup
if google_client_config:
    auth_module.auth_manager = GoogleAuthManager(
        client_config=google_client_config,
        redirect_uri=f"http://localhost:{port or 8321}/auth/callback",
    )

app.dependency_overrides[auth_module.get_db] = get_db

# Protected auth routes (bearer token required)
for route in auth_module.router.routes:
    route.dependencies = [require_token]
app.include_router(auth_module.router)

# Callback route (unauthenticated — Google redirects browser here)
app.dependency_overrides[auth_module.get_db] = get_db
app.include_router(auth_module.callback_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_auth_routes.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/planner/api/auth.py src/planner/server.py tests/planner/test_auth_routes.py
git commit -m "feat(planner): add Google OAuth API routes with account management"
```

---

## Task 7: Events and Sync API Routes

**Files:**
- Create: `src/planner/api/events.py`
- Create: `src/planner/api/sync.py`
- Create: `src/planner/ingestion/sync_scheduler.py`
- Create: `tests/planner/test_events_routes.py`
- Create: `tests/planner/test_sync_routes.py`

- [ ] **Step 1: Write failing tests for events route**

Create `tests/planner/test_events_routes.py`:
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
    aid = db.add_account("user@gmail.com", "google", "gmail.readonly")
    db.upsert_event(
        account_id=aid, source="gcal", external_id="evt1",
        title="Meeting", start_time="2026-03-20T14:00:00Z",
        end_time="2026-03-20T15:00:00Z", event_type="meeting",
    )
    db.upsert_event(
        account_id=aid, source="gmail", external_id="mail1",
        title="Email Action", start_time="2026-03-21T10:00:00Z",
        end_time="2026-03-21T10:30:00Z", event_type="email",
    )
    db.close()


class TestEventsRoute:
    def test_get_all_events(self, client, auth_headers, seeded_db):
        resp = client.get("/api/events", headers=auth_headers)
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 2

    def test_filter_events_by_source(self, client, auth_headers, seeded_db):
        resp = client.get("/api/events?source=gcal", headers=auth_headers)
        events = resp.json()
        assert len(events) == 1
        assert events[0]["title"] == "Meeting"

    def test_filter_events_by_date(self, client, auth_headers, seeded_db):
        resp = client.get(
            "/api/events?start_after=2026-03-20&end_before=2026-03-21",
            headers=auth_headers,
        )
        events = resp.json()
        assert len(events) == 1
        assert events[0]["title"] == "Meeting"

    def test_events_require_auth(self, client):
        assert client.get("/api/events").status_code == 401
```

- [ ] **Step 2: Write failing tests for sync route**

Create `tests/planner/test_sync_routes.py`:
```python
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

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


class TestSyncRoutes:
    def test_get_sync_status(self, client, auth_headers):
        resp = client.get("/sync/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "accounts" in data

    def test_trigger_sync(self, client, auth_headers):
        resp = client.post("/sync/trigger", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "triggered"

    def test_sync_routes_require_auth(self, client):
        assert client.get("/sync/status").status_code == 401
        assert client.post("/sync/trigger").status_code == 401
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_events_routes.py tests/planner/test_sync_routes.py -v`
Expected: FAIL

- [ ] **Step 4: Implement events route**

Create `src/planner/api/events.py`:
```python
from fastapi import APIRouter, Depends, Query

from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


@router.get("/events")
def get_events(
    source: str | None = Query(None),
    start_after: str | None = Query(None),
    end_before: str | None = Query(None),
    db: PlannerDB = Depends(get_db),
):
    return db.get_events(source=source, start_after=start_after, end_before=end_before)
```

- [ ] **Step 5: Implement sync route**

Create `src/planner/api/sync.py`:
```python
from fastapi import APIRouter, Depends

from src.planner.db import PlannerDB

router = APIRouter(prefix="/sync")


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


sync_callback = None


@router.get("/status")
def sync_status(db: PlannerDB = Depends(get_db)):
    """Return sync status for all connected accounts."""
    accounts = db.list_accounts()
    return {
        "accounts": [
            {
                "email": a["email"],
                "last_sync": a["last_sync"],
                "provider": a["provider"],
            }
            for a in accounts
        ]
    }


@router.post("/trigger")
def trigger_sync(db: PlannerDB = Depends(get_db)):
    """Trigger an immediate sync of all sources."""
    if sync_callback:
        sync_callback()
    return {"status": "triggered"}
```

- [ ] **Step 6: Implement sync scheduler**

Create `src/planner/ingestion/sync_scheduler.py`:
```python
import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from src.planner.db import PlannerDB
from src.planner.ingestion.google_auth import GoogleAuthManager
from src.planner.ingestion.gcal import GCalSyncer
from src.planner.ingestion.gmail import GmailSyncer

logger = logging.getLogger(__name__)


class SyncScheduler:
    def __init__(self, db: PlannerDB, auth_manager: GoogleAuthManager | None = None):
        self._db = db
        self._auth_manager = auth_manager
        self._gcal_syncer = GCalSyncer(db)
        self._gmail_syncer = GmailSyncer(db)
        self._scheduler = BackgroundScheduler()
        self._lock = threading.Lock()

    def start(self, interval_minutes: int = 15) -> None:
        """Start periodic sync job."""
        self._scheduler.add_job(
            self.sync_all,
            "interval",
            minutes=interval_minutes,
            id="sync_all",
            replace_existing=True,
        )
        self._scheduler.start()

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def sync_all(self) -> dict[str, int]:
        """Sync all connected accounts. Returns dict of email -> event count."""
        if not self._auth_manager:
            return {}

        with self._lock:
            results = {}
            accounts = self._db.list_accounts()

            for account in accounts:
                email = account["email"]
                try:
                    creds = self._auth_manager.refresh_if_expired(email)
                    if creds is None:
                        logger.warning("No credentials for %s, skipping", email)
                        continue

                    from googleapiclient.discovery import build

                    # Sync Calendar
                    cal_service = build("calendar", "v3", credentials=creds)
                    cal_count = self._gcal_syncer.sync_account(account["id"], cal_service)

                    # Sync Gmail
                    gmail_service = build("gmail", "v1", credentials=creds)
                    gmail_count = self._gmail_syncer.sync_account(account["id"], gmail_service)

                    results[email] = cal_count + gmail_count
                    logger.info("Synced %s: %d cal + %d gmail events", email, cal_count, gmail_count)

                except Exception as e:
                    logger.error("Failed to sync %s: %s", email, e)
                    results[email] = -1

            return results
```

- [ ] **Step 7: Register new routers in server.py**

Add to `src/planner/server.py` imports:
```python
from src.planner.api import events as events_module
from src.planner.api import sync as sync_module
from src.planner.ingestion.sync_scheduler import SyncScheduler
```

In `create_app`, add after auth router registration:
```python
# Events and sync routes
app.dependency_overrides[events_module.get_db] = get_db
for route in events_module.router.routes:
    route.dependencies = [require_token]
app.include_router(events_module.router)

app.dependency_overrides[sync_module.get_db] = get_db
for route in sync_module.router.routes:
    route.dependencies = [require_token]

# Sync scheduler
scheduler = SyncScheduler(db, auth_module.auth_manager)
scheduler.start()
sync_module.sync_callback = scheduler.sync_all
app.include_router(sync_module.router)
```

In the shutdown handler, add: `scheduler.stop()`

- [ ] **Step 8: Run all tests to verify they pass**

Run: `python -m pytest tests/planner/ -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
git add src/planner/api/events.py src/planner/api/sync.py src/planner/ingestion/sync_scheduler.py src/planner/server.py tests/planner/test_events_routes.py tests/planner/test_sync_routes.py
git commit -m "feat(planner): add events API, sync API, and background sync scheduler"
```

---

## Task 8: Frontend — Accounts Management

**Files:**
- Create: `frontend/src/hooks/useAccounts.ts`
- Create: `frontend/src/components/AccountsPanel.tsx`
- Modify: `frontend/src/components/SettingsView.tsx`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add TypeScript types**

Add to `frontend/src/types/index.ts`:
```typescript
export interface Account {
  id: number
  email: string
  provider: string
  last_sync: string | null
  created_at: string
}

export interface CalendarEvent {
  id: number
  source: string
  title: string
  description: string | null
  start_time: string
  end_time: string | null
  all_day: boolean
  location: string | null
  event_type: string | null
}

export interface SyncStatus {
  accounts: {
    email: string
    last_sync: string | null
    provider: string
  }[]
}
```

- [ ] **Step 2: Create accounts hook**

Create `frontend/src/hooks/useAccounts.ts`:
```typescript
import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'
import type { Account } from '../types'

export function useAccounts() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<Account[]>('/auth/accounts')
      setAccounts(data)
    } catch (err) {
      console.error('Failed to load accounts:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const addAccount = useCallback(async () => {
    try {
      const data = await apiFetch<{ auth_url: string }>('/auth/google')
      window.open(data.auth_url, '_blank')
    } catch (err) {
      console.error('Failed to initiate OAuth:', err)
    }
  }, [])

  const removeAccount = useCallback(async (id: number) => {
    await apiFetch(`/auth/accounts/${id}`, { method: 'DELETE' })
    setAccounts(prev => prev.filter(a => a.id !== id))
  }, [])

  return { accounts, loading, addAccount, removeAccount, reload: load }
}
```

- [ ] **Step 3: Create AccountsPanel component**

Create `frontend/src/components/AccountsPanel.tsx`:
```tsx
import { useAccounts } from '../hooks/useAccounts'

export default function AccountsPanel() {
  const { accounts, loading, addAccount, removeAccount } = useAccounts()

  if (loading) return <div className="text-gray-400">Loading accounts...</div>

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold">Connected Accounts</h3>
        <button
          onClick={addAccount}
          className="px-4 py-1.5 bg-accent hover:bg-blue-700 rounded text-sm text-white transition-colors"
        >
          + Add Google Account
        </button>
      </div>

      {accounts.length === 0 ? (
        <p className="text-sm text-gray-400">
          No accounts connected. Add a Google account to sync your calendar and email.
        </p>
      ) : (
        <div className="space-y-2">
          {accounts.map((account) => (
            <div
              key={account.id}
              className="flex items-center justify-between p-3 bg-gray-800 rounded-lg"
            >
              <div>
                <p className="text-white text-sm font-medium">{account.email}</p>
                <p className="text-xs text-gray-400">
                  {account.last_sync
                    ? `Last synced: ${new Date(account.last_sync).toLocaleString()}`
                    : 'Never synced'}
                </p>
              </div>
              <button
                onClick={() => removeAccount(account.id)}
                className="text-red-400 hover:text-red-300 text-sm transition-colors"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Update SettingsView to include AccountsPanel**

In `frontend/src/components/SettingsView.tsx`, replace the placeholder "Connected Accounts" section at the bottom with:

```tsx
import AccountsPanel from './AccountsPanel'
```

And replace the placeholder div:
```tsx
<div className="mt-10 border-t border-gray-700 pt-6">
  <AccountsPanel />
</div>
```

- [ ] **Step 5: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 6: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add Google account management UI with OAuth flow"
```

---

## Task 9: Frontend — Calendar Event Rendering

**Files:**
- Create: `frontend/src/hooks/useEvents.ts`
- Modify: `frontend/src/components/CalendarView.tsx`

- [ ] **Step 1: Create events hook**

Create `frontend/src/hooks/useEvents.ts`:
```typescript
import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'
import type { CalendarEvent } from '../types'

export function useEvents(startAfter?: string, endBefore?: string) {
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (startAfter) params.set('start_after', startAfter)
      if (endBefore) params.set('end_before', endBefore)
      const query = params.toString()
      const url = `/api/events${query ? `?${query}` : ''}`
      const data = await apiFetch<CalendarEvent[]>(url)
      setEvents(data)
    } catch (err) {
      console.error('Failed to load events:', err)
    } finally {
      setLoading(false)
    }
  }, [startAfter, endBefore])

  useEffect(() => { load() }, [load])

  return { events, loading, reload: load }
}
```

- [ ] **Step 2: Update CalendarView to render events**

Replace `frontend/src/components/CalendarView.tsx`:
```tsx
import { useMemo } from 'react'
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import { useEvents } from '../hooks/useEvents'
import type { CalendarEvent } from '../types'

interface CalendarViewProps {
  mode: 'day' | 'week'
}

const SOURCE_COLORS: Record<string, string> = {
  gcal: '#22c55e',
  gmail: '#3b82f6',
  canvas: '#f59e0b',
  manual: '#a855f7',
}

function toFullCalendarEvent(event: CalendarEvent) {
  return {
    id: String(event.id),
    title: event.title,
    start: event.start_time,
    end: event.end_time || undefined,
    allDay: event.all_day,
    backgroundColor: SOURCE_COLORS[event.source] || '#6b7280',
    borderColor: SOURCE_COLORS[event.source] || '#6b7280',
    extendedProps: {
      source: event.source,
      location: event.location,
      description: event.description,
    },
  }
}

export default function CalendarView({ mode }: CalendarViewProps) {
  const initialView = mode === 'day' ? 'timeGridDay' : 'timeGridWeek'
  const { events } = useEvents()

  const calendarEvents = useMemo(
    () => events.map(toFullCalendarEvent),
    [events]
  )

  return (
    <div className="h-full">
      <FullCalendar
        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
        initialView={initialView}
        headerToolbar={{
          left: 'prev,next today',
          center: 'title',
          right: 'timeGridDay,timeGridWeek',
        }}
        editable={mode === 'day'}
        selectable={mode === 'day'}
        nowIndicator={true}
        slotMinTime="06:00:00"
        slotMaxTime="24:00:00"
        height="100%"
        events={calendarEvents}
      />
    </div>
  )
}
```

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): render synced events on calendar with source-based coloring"
```

---

## Task 10: Google OAuth Client Config Setup

**Files:**
- Modify: `src/planner/server.py`
- Modify: `frontend/src/components/SettingsView.tsx`

This task handles how the user provides their Google Cloud OAuth credentials (client_id and client_secret). The app needs these to initiate OAuth flows.

- [ ] **Step 1: Add client config loading from preferences**

In `src/planner/server.py`, modify `create_app` to load Google client config from a JSON file in the app data directory:

```python
import json

# In create_app, after DB init:
google_config_path = Path(db_path).parent / "google_client_config.json"
if google_client_config is None and google_config_path.exists():
    with open(google_config_path) as f:
        google_client_config = json.load(f)
```

- [ ] **Step 2: Add a setup instruction to SettingsView**

In `frontend/src/components/SettingsView.tsx`, add a note below the AccountsPanel explaining where to place the Google credentials file:

```tsx
<p className="text-xs text-gray-500 mt-2">
  To connect Google accounts, place your Google Cloud OAuth credentials file as
  "google_client_config.json" in the app data directory, then restart the planner.
</p>
```

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npm run build`

- [ ] **Step 4: Commit**

```bash
git add src/planner/server.py frontend/src/
git commit -m "feat(planner): load Google OAuth client config from app data directory"
```

---

## Task 11: Run All Tests and Final Build

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/planner/ -v`
Expected: All tests pass

- [ ] **Step 2: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit built frontend**

```bash
git add frontend/dist/
git commit -m "chore: rebuild frontend with Google integration UI"
```

- [ ] **Step 4: Fix any failures and re-run**

```bash
git add -A
git commit -m "fix: resolve test failures from Phase 2 integration"
```
