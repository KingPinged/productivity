# AI Scheduling Assistant — Phase 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the FastAPI backend, SQLite database, pywebview window, and basic React calendar shell — the infrastructure all future phases build on.

**Architecture:** FastAPI runs as a subprocess launched by the existing Tkinter app on `127.0.0.1:8321`. It serves a pre-built React frontend (Vite + Tailwind + FullCalendar) as static files, displayed in a pywebview window. A per-session bearer token secures all endpoints. SQLite stores schedule data, preferences, and account metadata. The existing extension server gets a new `/usage` endpoint for cross-process data sharing.

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, SQLite (aiosqlite), cryptography (Fernet), pywebview, React 18, TypeScript, Vite, Tailwind CSS, FullCalendar, keyring

**Spec:** `docs/superpowers/specs/2026-03-19-ai-scheduling-assistant-design.md`

---

## File Structure

### New Python Files (Backend)

| File | Responsibility |
|------|---------------|
| `src/planner/__init__.py` | Package init |
| `src/planner/server.py` | FastAPI app factory, middleware, static file serving, startup/shutdown |
| `src/planner/db.py` | SQLite connection manager, schema migrations, table creation |
| `src/planner/encryption.py` | Fernet key management via OS keyring, encrypt/decrypt helpers |
| `src/planner/api/__init__.py` | API router registration |
| `src/planner/api/health.py` | `GET /health` (unauthenticated) |
| `src/planner/api/preferences.py` | `GET/PATCH /api/preferences` |
| `src/planner/api/schedule.py` | `GET /api/schedule/:date` (stub returning empty for Phase 1) |
| `src/planner/api/auth_middleware.py` | Bearer token validation dependency |
| `src/ui/planner_window.py` | pywebview launcher, token injection |

### Modified Python Files

| File | Change |
|------|--------|
| `src/core/extension_server.py` | Add `GET /usage` endpoint returning usage_data summary |
| `src/ui/tray_icon.py` | Add "Open Planner" menu item |
| `src/app.py` | Launch FastAPI subprocess + pywebview window |
| `requirements.txt` | Add fastapi, uvicorn, aiosqlite, pywebview, keyring, cryptography |

### New Frontend Files

| File | Responsibility |
|------|---------------|
| `frontend/package.json` | Dependencies and scripts |
| `frontend/tsconfig.json` | TypeScript config |
| `frontend/vite.config.ts` | Vite build config, proxy for dev |
| `frontend/tailwind.config.js` | Tailwind theme |
| `frontend/postcss.config.js` | PostCSS for Tailwind |
| `frontend/index.html` | HTML shell with token injection slot |
| `frontend/src/main.tsx` | React entry point |
| `frontend/src/App.tsx` | Root component with sidebar + router |
| `frontend/src/api/client.ts` | Fetch wrapper with bearer token |
| `frontend/src/components/Sidebar.tsx` | Navigation sidebar with What's Next panel |
| `frontend/src/components/CalendarView.tsx` | FullCalendar day/week view wrapper |
| `frontend/src/components/SettingsView.tsx` | Preferences form (wake/sleep time, etc.) |
| `frontend/src/hooks/usePreferences.ts` | Preferences data fetching hook |
| `frontend/src/hooks/useSchedule.ts` | Schedule data fetching hook |
| `frontend/src/types/index.ts` | TypeScript interfaces |
| `frontend/src/index.css` | Tailwind base imports + custom styles |

### Test Files

| File | Tests |
|------|-------|
| `tests/planner/test_db.py` | Schema creation, migrations, CRUD operations |
| `tests/planner/test_encryption.py` | Fernet key storage/retrieval, encrypt/decrypt round-trip |
| `tests/planner/test_server.py` | Health endpoint, auth middleware, preferences API, static serving |
| `tests/planner/test_auth_middleware.py` | Token validation, rejection of invalid tokens |
| `tests/planner/test_extension_usage.py` | New /usage endpoint on extension server |

---

## Task 1: Install Dependencies

**Files:**
- Modify: `requirements.txt`
- Create: `frontend/package.json`

- [ ] **Step 1: Add Python dependencies to requirements.txt**

Append to `requirements.txt`:
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
aiosqlite>=0.20.0
pywebview>=5.0
keyring>=25.0.0
cryptography>=43.0.0
```

- [ ] **Step 2: Install Python dependencies**

Run: `pip install -r requirements.txt`
Expected: All packages install successfully

- [ ] **Step 3: Create frontend/package.json**

```json
{
  "name": "productivity-planner",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@fullcalendar/core": "^6.1.15",
    "@fullcalendar/daygrid": "^6.1.15",
    "@fullcalendar/timegrid": "^6.1.15",
    "@fullcalendar/interaction": "^6.1.15",
    "@fullcalendar/react": "^6.1.15",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.16",
    "typescript": "^5.6.3",
    "vite": "^6.0.3"
  }
}
```

- [ ] **Step 4: Install frontend dependencies**

Run: `cd frontend && npm install`
Expected: `node_modules` created, no errors

- [ ] **Step 5: Commit**

```bash
git add requirements.txt frontend/package.json frontend/package-lock.json
git commit -m "chore: add backend and frontend dependencies for planner"
```

---

## Task 2: SQLite Database Layer

**Files:**
- Create: `src/planner/__init__.py`
- Create: `src/planner/db.py`
- Create: `tests/planner/__init__.py`
- Create: `tests/planner/test_db.py`

- [ ] **Step 1: Create package init files**

Create `src/planner/__init__.py` (empty file).
Create `tests/planner/__init__.py` (empty file).

- [ ] **Step 2: Write failing tests for database schema creation**

Create `tests/planner/test_db.py`:
```python
import os
import sqlite3
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
    return database


class TestSchemaCreation:
    def test_creates_all_tables(self, db, db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        expected = {
            "accounts",
            "canvas_configs",
            "events",
            "tasks",
            "schedule_blocks",
            "reminders",
            "preferences",
            "ai_context_cache",
            "schema_version",
        }
        assert expected.issubset(tables)

    def test_initialize_is_idempotent(self, db):
        db.initialize()
        db.initialize()

    def test_schema_version_is_set(self, db, db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT version FROM schema_version")
        version = cursor.fetchone()[0]
        conn.close()
        assert version == 1


class TestPreferencesCRUD:
    def test_set_and_get_preference(self, db):
        db.set_preference("wake_time", "07:00")
        assert db.get_preference("wake_time") == "07:00"

    def test_get_missing_preference_returns_none(self, db):
        assert db.get_preference("nonexistent") is None

    def test_get_preference_with_default(self, db):
        assert db.get_preference("missing", "fallback") == "fallback"

    def test_update_existing_preference(self, db):
        db.set_preference("wake_time", "07:00")
        db.set_preference("wake_time", "08:00")
        assert db.get_preference("wake_time") == "08:00"

    def test_get_all_preferences(self, db):
        db.set_preference("wake_time", "07:00")
        db.set_preference("sleep_time", "23:00")
        prefs = db.get_all_preferences()
        assert prefs == {"wake_time": "07:00", "sleep_time": "23:00"}

    def test_get_all_preferences_empty(self, db):
        assert db.get_all_preferences() == {}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.planner.db'`

- [ ] **Step 4: Implement PlannerDB**

Create `src/planner/db.py`:
```python
import json
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL DEFAULT 'google',
    scopes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_sync TIMESTAMP,
    deleted_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS canvas_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canvas_url TEXT NOT NULL,
    session_cookies TEXT NOT NULL,
    last_sync TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'active',
    deleted_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER REFERENCES accounts(id),
    source TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    all_day INTEGER DEFAULT 0,
    recurring_rule TEXT,
    location TEXT,
    event_type TEXT,
    raw_data TEXT,
    synced_at TIMESTAMP,
    UNIQUE(source, external_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    course TEXT,
    deadline TIMESTAMP,
    estimated_minutes INTEGER,
    priority INTEGER DEFAULT 3,
    status TEXT NOT NULL DEFAULT 'pending',
    grade_weight REAL,
    current_grade TEXT,
    ai_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(source, external_id)
);

CREATE TABLE IF NOT EXISTS schedule_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id),
    date DATE NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    block_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    ai_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_block_id INTEGER REFERENCES schedule_blocks(id),
    task_id INTEGER REFERENCES tasks(id),
    remind_at TIMESTAMP NOT NULL,
    reminder_type TEXT NOT NULL,
    message TEXT NOT NULL,
    urgent INTEGER DEFAULT 0,
    fired INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS ai_context_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    context_hash TEXT,
    schedule_json TEXT,
    tokens_used INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class PlannerDB:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        conn = self._get_conn()
        conn.executescript(SCHEMA_SQL)
        cursor = conn.execute("SELECT COUNT(*) FROM schema_version")
        if cursor.fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def set_preference(self, key: str, value: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO preferences (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()

    def get_preference(self, key: str, default: str | None = None) -> str | None:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT value FROM preferences WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row[0] if row else default

    def get_all_preferences(self) -> dict[str, str]:
        conn = self._get_conn()
        cursor = conn.execute("SELECT key, value FROM preferences")
        return {row[0]: row[1] for row in cursor.fetchall()}

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_db.py -v`
Expected: All 7 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/planner/__init__.py src/planner/db.py tests/planner/__init__.py tests/planner/test_db.py
git commit -m "feat(planner): add SQLite database layer with schema and preferences CRUD"
```

---

## Task 3: Encryption Helpers

**Files:**
- Create: `src/planner/encryption.py`
- Create: `tests/planner/test_encryption.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_encryption.py`:
```python
import pytest
from unittest.mock import patch, MagicMock

from src.planner.encryption import EncryptionManager


@pytest.fixture
def manager():
    with patch("src.planner.encryption.keyring") as mock_keyring:
        mock_keyring.get_password.return_value = None
        mgr = EncryptionManager(service_name="test-planner")
        yield mgr


class TestEncryptionManager:
    def test_encrypt_decrypt_roundtrip(self, manager):
        plaintext = "my-secret-token-12345"
        encrypted = manager.encrypt(plaintext)
        assert encrypted != plaintext
        decrypted = manager.decrypt(encrypted)
        assert decrypted == plaintext

    def test_encrypt_produces_different_output_each_call(self, manager):
        plaintext = "same-input"
        a = manager.encrypt(plaintext)
        b = manager.encrypt(plaintext)
        assert a != b

    def test_decrypt_invalid_data_raises(self, manager):
        with pytest.raises(Exception):
            manager.decrypt("not-valid-fernet-data")

    def test_key_is_stored_in_keyring(self):
        with patch("src.planner.encryption.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = None
            EncryptionManager(service_name="test-planner")
            mock_keyring.set_password.assert_called_once()
            call_args = mock_keyring.set_password.call_args
            assert call_args[0][0] == "test-planner"
            assert call_args[0][1] == "fernet-key"

    def test_existing_key_is_reused(self):
        from cryptography.fernet import Fernet

        existing_key = Fernet.generate_key().decode()
        with patch("src.planner.encryption.keyring") as mock_keyring:
            mock_keyring.get_password.return_value = existing_key
            mgr = EncryptionManager(service_name="test-planner")
            mock_keyring.set_password.assert_not_called()
            encrypted = mgr.encrypt("test")
            assert mgr.decrypt(encrypted) == "test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_encryption.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement EncryptionManager**

Create `src/planner/encryption.py`:
```python
import keyring
from cryptography.fernet import Fernet


class EncryptionManager:
    def __init__(self, service_name: str = "productivity-planner"):
        self._service_name = service_name
        self._fernet = Fernet(self._get_or_create_key())

    def _get_or_create_key(self) -> bytes:
        stored_key = keyring.get_password(self._service_name, "fernet-key")
        if stored_key:
            return stored_key.encode()
        new_key = Fernet.generate_key()
        keyring.set_password(self._service_name, "fernet-key", new_key.decode())
        return new_key

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/planner/test_encryption.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/planner/encryption.py tests/planner/test_encryption.py
git commit -m "feat(planner): add encryption manager using OS keyring for Fernet key storage"
```

---

## Task 4: FastAPI Server with Auth Middleware

**Files:**
- Create: `src/planner/api/__init__.py`
- Create: `src/planner/api/auth_middleware.py`
- Create: `src/planner/api/health.py`
- Create: `src/planner/server.py`
- Create: `tests/planner/test_server.py`
- Create: `tests/planner/test_auth_middleware.py`

- [ ] **Step 1: Write failing tests for auth middleware**

Create `tests/planner/test_auth_middleware.py`:
```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.planner.api.auth_middleware import create_token_dependency


@pytest.fixture
def app_with_auth():
    app = FastAPI()
    valid_token = "test-secret-token-abc123"
    require_token = create_token_dependency(valid_token)

    @app.get("/protected")
    def protected(token: str = require_token):
        return {"status": "ok"}

    return app, valid_token


@pytest.fixture
def client(app_with_auth):
    app, _ = app_with_auth
    return TestClient(app)


@pytest.fixture
def token(app_with_auth):
    _, t = app_with_auth
    return t


class TestAuthMiddleware:
    def test_valid_token_allows_access(self, client, token):
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_missing_header_returns_401(self, client):
        resp = client.get("/protected")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client):
        resp = client.get("/protected", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    def test_malformed_header_returns_401(self, client):
        resp = client.get("/protected", headers={"Authorization": "NotBearer token"})
        assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_auth_middleware.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement auth middleware**

Create `src/planner/api/__init__.py` (empty file).

Create `src/planner/api/auth_middleware.py`:
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_security = HTTPBearer(auto_error=False)


def create_token_dependency(expected_token: str):
    def verify_token(
        credentials: HTTPAuthorizationCredentials | None = Depends(_security),
    ) -> str:
        if credentials is None or credentials.credentials != expected_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing token",
            )
        return credentials.credentials

    return Depends(verify_token)
```

- [ ] **Step 4: Run auth tests to verify they pass**

Run: `python -m pytest tests/planner/test_auth_middleware.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Write failing tests for server (health + preferences)**

Create `tests/planner/test_server.py`:
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
    return "test-token-xyz"


@pytest.fixture
def client(db_path, token):
    app = create_app(db_path=db_path, auth_token=token)
    return TestClient(app)


@pytest.fixture
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_health_requires_no_auth(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200


class TestPreferencesAPI:
    def test_get_preferences_empty(self, client, auth_headers):
        resp = client.get("/api/preferences", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_set_and_get_preferences(self, client, auth_headers):
        resp = client.patch(
            "/api/preferences",
            json={"wake_time": "07:00", "sleep_time": "23:00"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        resp = client.get("/api/preferences", headers=auth_headers)
        data = resp.json()
        assert data["wake_time"] == "07:00"
        assert data["sleep_time"] == "23:00"

    def test_update_existing_preference(self, client, auth_headers):
        client.patch(
            "/api/preferences",
            json={"wake_time": "07:00"},
            headers=auth_headers,
        )
        client.patch(
            "/api/preferences",
            json={"wake_time": "08:30"},
            headers=auth_headers,
        )
        resp = client.get("/api/preferences", headers=auth_headers)
        assert resp.json()["wake_time"] == "08:30"

    def test_preferences_require_auth(self, client):
        resp = client.get("/api/preferences")
        assert resp.status_code == 401


class TestScheduleStub:
    def test_get_schedule_returns_empty(self, client, auth_headers):
        resp = client.get("/api/schedule/2026-03-19", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["date"] == "2026-03-19"
        assert data["blocks"] == []

    def test_schedule_requires_auth(self, client):
        resp = client.get("/api/schedule/2026-03-19")
        assert resp.status_code == 401
```

- [ ] **Step 6: Run server tests to verify they fail**

Run: `python -m pytest tests/planner/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 7: Implement health endpoint**

Create `src/planner/api/health.py`:
```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 8: Implement preferences endpoint**

Create `src/planner/api/preferences.py`:
```python
from fastapi import APIRouter, Depends

from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


@router.get("/preferences")
def get_preferences(db: PlannerDB = Depends(get_db)):
    return db.get_all_preferences()


@router.patch("/preferences")
def update_preferences(prefs: dict[str, str], db: PlannerDB = Depends(get_db)):
    for key, value in prefs.items():
        db.set_preference(key, value)
    return {"status": "updated", "count": len(prefs)}
```

- [ ] **Step 9: Implement schedule stub endpoint**

Create `src/planner/api/schedule.py`:
```python
from fastapi import APIRouter, Depends

from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


@router.get("/schedule/{date}")
def get_schedule(date: str, db: PlannerDB = Depends(get_db)):
    return {"date": date, "blocks": []}
```

- [ ] **Step 10: Implement FastAPI app factory**

Create `src/planner/server.py`:
```python
import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.planner.api.auth_middleware import create_token_dependency
from src.planner.api.health import router as health_router
from src.planner.api import preferences as prefs_module
from src.planner.api import schedule as schedule_module
from src.planner.db import PlannerDB

STATIC_DIR = Path(__file__).parent.parent.parent / "frontend" / "dist"


def create_app(
    db_path: str | None = None,
    auth_token: str | None = None,
    static_dir: Path | None = None,
) -> FastAPI:
    if auth_token is None:
        auth_token = secrets.token_urlsafe(32)

    app = FastAPI(title="Productivity Planner")
    app.state.auth_token = auth_token

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    require_token = create_token_dependency(auth_token)

    if db_path is None:
        from src.utils.constants import APP_DATA_DIR
        db_path = str(Path(APP_DATA_DIR) / "planner.db")

    db = PlannerDB(db_path)
    db.initialize()

    def get_db() -> PlannerDB:
        return db

    prefs_module.get_db = get_db
    schedule_module.get_db = get_db
    app.dependency_overrides[prefs_module.get_db] = get_db
    app.dependency_overrides[schedule_module.get_db] = get_db

    app.include_router(health_router)

    for route in prefs_module.router.routes:
        route.dependencies = [require_token]
    app.include_router(prefs_module.router)

    for route in schedule_module.router.routes:
        route.dependencies = [require_token]
    app.include_router(schedule_module.router)

    serve_dir = static_dir or STATIC_DIR
    if serve_dir.exists():
        # Serve index.html with token injected (replaces placeholder)
        index_path = serve_dir / "index.html"

        @app.get("/")
        def serve_index():
            from fastapi.responses import HTMLResponse

            html = index_path.read_text()
            html = html.replace("__TOKEN_PLACEHOLDER__", auth_token)
            return HTMLResponse(html)

        app.mount("/", StaticFiles(directory=str(serve_dir), html=False), name="static")

    @app.on_event("shutdown")
    def shutdown():
        db.close()

    return app


def run_server(db_path: str, auth_token: str, host: str = "127.0.0.1", port: int = 8321):
    """Entry point for subprocess launch."""
    import uvicorn

    app = create_app(db_path=db_path, auth_token=auth_token)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    import sys

    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    auth_token = sys.argv[2] if len(sys.argv) > 2 else None
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 8321
    run_server(db_path=db_path, auth_token=auth_token, port=port)
```

- [ ] **Step 11: Run all server tests to verify they pass**

Run: `python -m pytest tests/planner/test_server.py tests/planner/test_auth_middleware.py -v`
Expected: All tests PASS

- [ ] **Step 12: Commit**

```bash
git add src/planner/api/ src/planner/server.py tests/planner/test_server.py tests/planner/test_auth_middleware.py
git commit -m "feat(planner): add FastAPI server with auth middleware, health, preferences, and schedule stub"
```

---

## Task 5: Usage Endpoint on Extension Server

**Files:**
- Modify: `src/core/extension_server.py`
- Create: `tests/planner/test_extension_usage.py`

- [ ] **Step 1: Write failing test for /usage endpoint**

Create `tests/planner/test_extension_usage.py`:
```python
import json
import urllib.request

import pytest

from src.core.extension_server import ExtensionServer


@pytest.fixture
def server():
    srv = ExtensionServer()
    srv.start()
    yield srv
    srv.stop()


class TestUsageEndpoint:
    def test_usage_returns_json(self, server):
        port = server.get_port()
        url = f"http://127.0.0.1:{port}/usage"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            assert "today" in data
            assert "apps" in data["today"]
            assert "websites" in data["today"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/planner/test_extension_usage.py -v`
Expected: FAIL — HTTP 404 or connection error (endpoint doesn't exist yet)

- [ ] **Step 3: Add /usage endpoint to extension server**

In `src/core/extension_server.py`, add `/usage` to the `do_GET` method's path routing (around the existing GET handlers), and add a `_handle_usage` method:

Add `'usage'` to the GET path check, and add this handler method to `ExtensionRequestHandler`:

```python
def _handle_usage(self):
    """Return usage data summary for the planner backend."""
    callback = ExtensionRequestHandler.usage_data_callback
    if callback:
        data = callback()
    else:
        data = {"today": {"apps": {}, "websites": {}}}

    self.send_response(200)
    self.send_header('Content-Type', 'application/json')
    self._send_cors_headers()
    self.end_headers()
    self.wfile.write(json.dumps(data).encode())
```

Add to `ExtensionServer` class:

```python
@staticmethod
def set_usage_data_callback(callback):
    ExtensionRequestHandler.usage_data_callback = callback
```

Add class variable to `ExtensionRequestHandler`:

```python
usage_data_callback = None
```

In the `do_GET` method, add the path check:
```python
elif path == '/usage':
    self._handle_usage()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/planner/test_extension_usage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/extension_server.py tests/planner/test_extension_usage.py
git commit -m "feat(extension): add GET /usage endpoint for planner data sharing"
```

---

## Task 6: React Frontend Shell

**Files:**
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/index.css`
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: Create Vite config**

Create `frontend/vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8321',
      '/health': 'http://127.0.0.1:8321',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
```

- [ ] **Step 2: Create TypeScript config**

Create `frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Create Tailwind and PostCSS configs**

Create `frontend/tailwind.config.js`:
```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: '#1a1a2e',
        'surface-light': '#16213e',
        accent: '#0f3460',
        highlight: '#e94560',
      },
    },
  },
  plugins: [],
}
```

Create `frontend/postcss.config.js`:
```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

- [ ] **Step 4: Create index.html with token injection**

Create `frontend/index.html`:
```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Productivity Planner</title>
    <script>window.__PLANNER_TOKEN__ = "__TOKEN_PLACEHOLDER__";</script>
  </head>
  <body class="bg-surface text-gray-100 m-0 p-0 overflow-hidden">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Create TypeScript types**

Create `frontend/src/types/index.ts`:
```typescript
export interface ScheduleBlock {
  id: number
  task_id: number | null
  date: string
  start_time: string
  end_time: string
  block_type: 'study' | 'meeting' | 'rest' | 'personal' | 'buffer'
  status: 'scheduled' | 'active' | 'completed' | 'skipped' | 'rescheduled'
  ai_reason: string | null
}

export interface DaySchedule {
  date: string
  blocks: ScheduleBlock[]
}

export interface Preferences {
  [key: string]: string
}
```

- [ ] **Step 6: Create API client**

Create `frontend/src/api/client.ts`:
```typescript
const getToken = (): string => {
  return (window as any).__PLANNER_TOKEN__ || ''
}

const BASE = ''

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
      ...options?.headers,
    },
  })
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status} ${resp.statusText}`)
  }
  return resp.json()
}
```

- [ ] **Step 7: Create CSS entry point**

Create `frontend/src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body, #root {
  height: 100%;
  width: 100%;
}
```

- [ ] **Step 8: Create main.tsx entry point**

Create `frontend/src/main.tsx`:
```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
```

- [ ] **Step 9: Create App.tsx with basic layout**

Create `frontend/src/App.tsx`:
```tsx
import { useState } from 'react'
import Sidebar from './components/Sidebar'
import CalendarView from './components/CalendarView'
import SettingsView from './components/SettingsView'

type View = 'today' | 'tasks' | 'week' | 'settings'

export default function App() {
  const [view, setView] = useState<View>('today')

  return (
    <div className="flex h-screen bg-surface">
      <Sidebar currentView={view} onNavigate={setView} />
      <main className="flex-1 overflow-auto p-6">
        {view === 'today' && <CalendarView mode="day" />}
        {view === 'week' && <CalendarView mode="week" />}
        {view === 'settings' && <SettingsView />}
        {view === 'tasks' && (
          <div className="text-gray-400 text-center mt-20">
            Tasks view — coming in Phase 5
          </div>
        )}
      </main>
    </div>
  )
}
```

- [ ] **Step 10: Commit**

```bash
git add frontend/vite.config.ts frontend/tsconfig.json frontend/tailwind.config.js frontend/postcss.config.js frontend/index.html frontend/src/
git commit -m "feat(frontend): scaffold React app with Vite, Tailwind, types, and API client"
```

---

## Task 7: React Components — Sidebar, Calendar, Settings

**Files:**
- Create: `frontend/src/components/Sidebar.tsx`
- Create: `frontend/src/components/CalendarView.tsx`
- Create: `frontend/src/components/SettingsView.tsx`
- Create: `frontend/src/hooks/usePreferences.ts`
- Create: `frontend/src/hooks/useSchedule.ts`

- [ ] **Step 1: Create data hooks**

Create `frontend/src/hooks/usePreferences.ts`:
```typescript
import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'
import type { Preferences } from '../types'

export function usePreferences() {
  const [prefs, setPrefs] = useState<Preferences>({})
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<Preferences>('/api/preferences')
      setPrefs(data)
    } catch (err) {
      console.error('Failed to load preferences:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const save = useCallback(async (updates: Preferences) => {
    await apiFetch('/api/preferences', {
      method: 'PATCH',
      body: JSON.stringify(updates),
    })
    setPrefs(prev => ({ ...prev, ...updates }))
  }, [])

  return { prefs, loading, save, reload: load }
}
```

Create `frontend/src/hooks/useSchedule.ts`:
```typescript
import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'
import type { DaySchedule } from '../types'

export function useSchedule(date: string) {
  const [schedule, setSchedule] = useState<DaySchedule | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<DaySchedule>(`/api/schedule/${date}`)
      setSchedule(data)
    } catch (err) {
      console.error('Failed to load schedule:', err)
    } finally {
      setLoading(false)
    }
  }, [date])

  useEffect(() => { load() }, [load])

  return { schedule, loading, reload: load }
}
```

- [ ] **Step 2: Create Sidebar component**

Create `frontend/src/components/Sidebar.tsx`:
```tsx
type View = 'today' | 'tasks' | 'week' | 'settings'

interface SidebarProps {
  currentView: View
  onNavigate: (view: View) => void
}

const navItems: { view: View; label: string; icon: string }[] = [
  { view: 'today', label: 'Today', icon: '\u2600' },
  { view: 'tasks', label: 'Tasks', icon: '\u2611' },
  { view: 'week', label: 'Week', icon: '\u{1F4C5}' },
  { view: 'settings', label: 'Settings', icon: '\u2699' },
]

export default function Sidebar({ currentView, onNavigate }: SidebarProps) {
  return (
    <aside className="w-56 bg-surface-light flex flex-col border-r border-gray-700">
      <div className="p-4 border-b border-gray-700">
        <h1 className="text-lg font-bold text-white">Planner</h1>
      </div>

      <nav className="flex-1 p-2 space-y-1">
        {navItems.map(({ view, label, icon }) => (
          <button
            key={view}
            onClick={() => onNavigate(view)}
            className={`w-full text-left px-3 py-2 rounded-lg flex items-center gap-2 transition-colors ${
              currentView === view
                ? 'bg-accent text-white'
                : 'text-gray-400 hover:bg-gray-700 hover:text-gray-200'
            }`}
          >
            <span>{icon}</span>
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="p-4 border-t border-gray-700">
        <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">
          What's Next
        </h3>
        <p className="text-sm text-gray-400">
          No tasks scheduled yet
        </p>
      </div>
    </aside>
  )
}
```

- [ ] **Step 3: Create CalendarView component**

Create `frontend/src/components/CalendarView.tsx`:
```tsx
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'

interface CalendarViewProps {
  mode: 'day' | 'week'
}

const BLOCK_COLORS: Record<string, string> = {
  study: '#3b82f6',
  meeting: '#22c55e',
  rest: '#f59e0b',
  personal: '#a855f7',
  buffer: '#6b7280',
}

export default function CalendarView({ mode }: CalendarViewProps) {
  const initialView = mode === 'day' ? 'timeGridDay' : 'timeGridWeek'

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
        events={[]}
      />
    </div>
  )
}
```

- [ ] **Step 4: Create SettingsView component**

Create `frontend/src/components/SettingsView.tsx`:
```tsx
import { useState, useEffect } from 'react'
import { usePreferences } from '../hooks/usePreferences'

const FIELDS = [
  { key: 'wake_time', label: 'Wake Time', type: 'time', default: '07:00' },
  { key: 'sleep_time', label: 'Sleep Time', type: 'time', default: '23:00' },
  { key: 'max_work_hours', label: 'Max Work Hours/Day', type: 'number', default: '8' },
  { key: 'break_frequency', label: 'Break Every (min)', type: 'number', default: '90' },
  { key: 'study_block_length', label: 'Study Block Length (min)', type: 'number', default: '60' },
  { key: 'schedule_style', label: 'Schedule Style', type: 'select', default: 'balanced', options: ['packed', 'balanced', 'relaxed'] },
] as const

export default function SettingsView() {
  const { prefs, loading, save } = usePreferences()
  const [form, setForm] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const initial: Record<string, string> = {}
    for (const field of FIELDS) {
      initial[field.key] = prefs[field.key] || field.default
    }
    setForm(initial)
  }, [prefs])

  const handleSave = async () => {
    setSaving(true)
    try {
      await save(form)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="text-gray-400">Loading...</div>

  return (
    <div className="max-w-lg">
      <h2 className="text-xl font-bold mb-6">Preferences</h2>

      <div className="space-y-4">
        {FIELDS.map((field) => (
          <div key={field.key}>
            <label className="block text-sm text-gray-400 mb-1">{field.label}</label>
            {field.type === 'select' ? (
              <select
                value={form[field.key] || ''}
                onChange={(e) => setForm({ ...form, [field.key]: e.target.value })}
                className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
              >
                {'options' in field && field.options.map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            ) : (
              <input
                type={field.type}
                value={form[field.key] || ''}
                onChange={(e) => setForm({ ...form, [field.key]: e.target.value })}
                className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-white"
              />
            )}
          </div>
        ))}
      </div>

      <button
        onClick={handleSave}
        disabled={saving}
        className="mt-6 px-6 py-2 bg-accent hover:bg-blue-700 rounded text-white font-medium disabled:opacity-50 transition-colors"
      >
        {saving ? 'Saving...' : 'Save Preferences'}
      </button>

      <div className="mt-10 border-t border-gray-700 pt-6">
        <h3 className="text-lg font-bold mb-4">Connected Accounts</h3>
        <p className="text-sm text-gray-400">
          Account management coming in Phase 2 (Google) and Phase 3 (Canvas).
        </p>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Build the frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds, `frontend/dist/` directory created with `index.html` and JS/CSS bundles

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ frontend/src/hooks/
git commit -m "feat(frontend): add Sidebar, CalendarView, SettingsView components with data hooks"
```

---

## Task 8: pywebview Launcher

**Files:**
- Create: `src/ui/planner_window.py`

- [ ] **Step 1: Implement pywebview launcher**

Create `src/ui/planner_window.py`:
```python
import threading

import webview


class PlannerWindow:
    def __init__(self, server_url: str, auth_token: str):
        self._server_url = server_url
        self._auth_token = auth_token
        self._window: webview.Window | None = None
        self._thread: threading.Thread | None = None

    def show(self) -> None:
        if self._window is not None:
            try:
                self._window.show()
                return
            except Exception:
                self._window = None

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self._window = webview.create_window(
            title="Productivity Planner",
            url=self._server_url,
            width=1200,
            height=800,
            min_size=(800, 600),
            text_select=True,
        )
        webview.start()

    def destroy(self) -> None:
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/planner_window.py
git commit -m "feat(ui): add pywebview planner window launcher"
```

---

## Task 9: Integrate into Existing App

**Files:**
- Modify: `src/app.py` (add planner subprocess launch + tray menu item)
- Modify: `src/ui/tray_icon.py` (add "Open Planner" menu item)

- [ ] **Step 1: Add "Open Planner" to tray icon**

In `src/ui/tray_icon.py`, add a new callback parameter to `__init__` and a new menu item.

Add `on_planner=None` parameter to `__init__`, store as `self.on_planner = on_planner`.

In `_setup_icon`, add before the Settings menu item:
```python
MenuItem("Open Planner", self._on_planner_click),
```

Add callback method:
```python
def _on_planner_click(self, icon=None, item=None):
    if self.on_planner:
        if self.root:
            self.root.after(0, self.on_planner)
        else:
            self.on_planner()
```

- [ ] **Step 2: Add planner launch to ProductivityApp**

In `src/app.py`, add planner initialization. Add these imports at the top:
```python
import secrets
import subprocess
import sys
import urllib.request
from pathlib import Path
```

Add a method `_init_planner` to `ProductivityApp`:
```python
def _init_planner(self):
    """Launch the FastAPI planner backend as a subprocess."""
    from src.utils.constants import APP_DATA_DIR

    self._planner_token = secrets.token_urlsafe(32)
    self._planner_port = 8321
    db_path = str(Path(APP_DATA_DIR) / "planner.db")

    self._planner_process = subprocess.Popen(
        [
            sys.executable,
            "-m", "src.planner.server",
            db_path,
            self._planner_token,
            str(self._planner_port),
        ],
        cwd=str(Path(__file__).parent.parent),
    )

    self._wait_for_planner_health()

    from src.ui.planner_window import PlannerWindow
    self._planner_window = PlannerWindow(
        server_url=f"http://127.0.0.1:{self._planner_port}",
        auth_token=self._planner_token,
    )
```

Add health check method:
```python
def _wait_for_planner_health(self, timeout: int = 10):
    """Poll /health until the planner backend is ready."""
    import time
    url = f"http://127.0.0.1:{self._planner_port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception:
            pass
        time.sleep(0.5)
    print("Warning: Planner backend did not become ready in time")
```

Add method to open the planner:
```python
def _open_planner(self):
    if hasattr(self, '_planner_window') and self._planner_window:
        self._planner_window.show()
```

In `__init__`, call `self._init_planner()` after existing initialization.

In tray icon creation, pass `on_planner=self._open_planner`.

In `_on_exit`, add cleanup:
```python
if hasattr(self, '_planner_process') and self._planner_process:
    self._planner_process.terminate()
if hasattr(self, '_planner_window') and self._planner_window:
    self._planner_window.destroy()
```

- [ ] **Step 3: Wire up usage data callback**

In `src/app.py`, after extension server is started, add:
```python
def _get_usage_data():
    if self.usage_data:
        daily = self.usage_data.get_daily_stats()  # returns DailyUsage for today
        return {"today": daily.to_dict()}
    return {"today": {"date": "", "entries": {}, "total_app_seconds": 0, "total_website_seconds": 0}}

self.extension_server.set_usage_data_callback(_get_usage_data)
```

The `UsageData.get_daily_stats()` returns a `DailyUsage` dataclass with a `.to_dict()` method that serializes entries (each with name, category, seconds).

- [ ] **Step 4: Test manually**

Run the app and verify:
1. FastAPI backend starts (check `http://127.0.0.1:8321/health` returns `{"status":"ok"}`)
2. "Open Planner" appears in system tray menu
3. Clicking "Open Planner" opens the pywebview window with the React calendar UI
4. Settings view can save and load preferences
5. App shutdown cleanly terminates the planner subprocess

- [ ] **Step 5: Commit**

```bash
git add src/app.py src/ui/tray_icon.py
git commit -m "feat: integrate planner backend and webview into existing app lifecycle"
```

---

## Task 10: Build and Add Frontend to .gitignore

**Files:**
- Create: `frontend/.gitignore`
- Modify: `.gitignore` (if exists)

- [ ] **Step 1: Create frontend .gitignore**

Create `frontend/.gitignore`:
```
node_modules/
dist/
```

- [ ] **Step 2: Build frontend for distribution**

Run: `cd frontend && npm run build`
Expected: `frontend/dist/` created with production build

Note: The `dist/` folder should be committed so the app works without requiring Node.js at runtime. Remove `dist/` from `.gitignore` if needed, or add a build step to the app's setup.

- [ ] **Step 3: Commit**

```bash
git add frontend/.gitignore frontend/dist/
git commit -m "chore: add frontend gitignore and production build"
```

---

## Task 11: Run All Tests

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/planner/ -v`
Expected: All tests pass

- [ ] **Step 2: Fix any failures and re-run**

- [ ] **Step 3: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: resolve test failures from Phase 1 integration"
```
