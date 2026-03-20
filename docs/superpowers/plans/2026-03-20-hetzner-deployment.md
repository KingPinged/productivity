# Hetzner VPS Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the AI scheduling planner to a Hetzner CX22 VPS with JWT auth, PWA support, Web Push notifications, and Canvas cookie-paste scraping.

**Architecture:** Replace the static bearer token auth with JWT password login. Add PWA manifest + service worker for phone install. Add Web Push via VAPID keys + pywebpush for cross-device notifications. Replace Playwright Canvas scraper with requests-based scraping using pasted cookies. Package everything in a Docker container behind Nginx with Let's Encrypt SSL.

**Tech Stack:** PyJWT, pywebpush, Gunicorn, Docker, Nginx, Let's Encrypt, Service Workers

**Spec:** `docs/superpowers/specs/2026-03-20-hetzner-deployment-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/planner/api/login.py` | Password login endpoint, returns JWT |
| `src/planner/api/push.py` | Web Push subscription + VAPID key endpoint |
| `src/planner/ingestion/canvas_requests.py` | Canvas scraping via requests (no Playwright) |
| `frontend/public/manifest.json` | PWA manifest |
| `frontend/public/sw.js` | Service worker for caching + push |
| `frontend/public/icons/icon-192.png` | PWA icon 192x192 |
| `frontend/public/icons/icon-512.png` | PWA icon 512x512 |
| `frontend/src/components/LoginPage.tsx` | Login form component |
| `Dockerfile` | Container image |
| `docker-compose.yml` | Service orchestration |
| `run_server.py` | Gunicorn entry point |
| `nginx/planner.conf` | Nginx reverse proxy config |
| `deploy.sh` | VPS setup script |

### Modified Files

| File | Change |
|------|--------|
| `src/planner/api/auth_middleware.py` | JWT validation instead of static token |
| `src/planner/server.py` | JWT auth, push routes, login route, env-based config |
| `src/planner/db.py` | Add push_subscriptions table |
| `src/planner/reminders/service.py` | Send Web Push alongside system notifications |
| `src/planner/reminders/notifier.py` | Add web push dispatch method |
| `src/planner/ingestion/canvas.py` | Use requests instead of Playwright |
| `frontend/index.html` | PWA meta tags, manifest link |
| `frontend/src/App.tsx` | Login gate, push subscription prompt |
| `frontend/src/api/client.ts` | JWT token from localStorage instead of window global |
| `frontend/src/components/SettingsView.tsx` | Canvas cookie paste textarea |
| `requirements.txt` | Add PyJWT, pywebpush; remove playwright |

### Test Files

| File | Tests |
|------|-------|
| `tests/planner/test_jwt_auth.py` | JWT login, validation, rejection |
| `tests/planner/test_push.py` | Push subscription CRUD |
| `tests/planner/test_canvas_requests.py` | Canvas scraping via requests |

---

## Task 1: Add Dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Update requirements**

Replace `playwright>=1.48.0` with new deps. Add:
```
PyJWT>=2.8.0
pywebpush>=2.0.0
gunicorn>=22.0.0
```

Remove:
```
playwright>=1.48.0
```

- [ ] **Step 2: Install**

Run: `pip install PyJWT pywebpush gunicorn`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add JWT, pywebpush, gunicorn; remove playwright"
```

---

## Task 2: JWT Authentication

**Files:**
- Create: `src/planner/api/login.py`
- Modify: `src/planner/api/auth_middleware.py`
- Modify: `src/planner/server.py`
- Create: `tests/planner/test_jwt_auth.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_jwt_auth.py`:
```python
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("PLANNER_PASSWORD", "testpass123")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-key")

from src.planner.server import create_app


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def client(db_path):
    app = create_app(db_path=db_path)
    with TestClient(app) as c:
        yield c


def login(client):
    resp = client.post("/auth/login", json={"password": "testpass123"})
    return resp.json().get("token")


class TestJWTAuth:
    def test_login_with_correct_password(self, client):
        resp = client.post("/auth/login", json={"password": "testpass123"})
        assert resp.status_code == 200
        assert "token" in resp.json()

    def test_login_with_wrong_password(self, client):
        resp = client.post("/auth/login", json={"password": "wrong"})
        assert resp.status_code == 401

    def test_jwt_token_grants_access(self, client):
        token = login(client)
        resp = client.get("/api/preferences", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_no_token_returns_401(self, client):
        resp = client.get("/api/preferences")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client):
        resp = client.get("/api/preferences", headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 401

    def test_health_requires_no_auth(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/planner/test_jwt_auth.py -v`
Expected: FAIL

- [ ] **Step 3: Implement login endpoint**

Create `src/planner/api/login.py`:
```python
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/auth")

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 30
PLANNER_PASSWORD = os.environ.get("PLANNER_PASSWORD", "")


@router.post("/login")
def login(body: dict):
    """Authenticate with password, returns JWT."""
    password = body.get("password", "")
    if not PLANNER_PASSWORD or password != PLANNER_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid password")

    payload = {
        "sub": "planner-user",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"token": token}
```

- [ ] **Step 4: Replace auth middleware with JWT validation**

Replace `src/planner/api/auth_middleware.py`:
```python
import os

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_security = HTTPBearer(auto_error=False)

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"


def require_jwt(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing token",
        )
    try:
        payload = jwt.decode(
            credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
        return payload.get("sub", "")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# Backward compatibility — used in server.py route registration
def create_token_dependency(_token: str | None = None):
    """Returns a Depends that validates JWT. The _token arg is ignored (legacy)."""
    return Depends(require_jwt)
```

- [ ] **Step 5: Update server.py**

In `src/planner/server.py`:
- Remove `auth_token` parameter from `create_app` signature
- Remove `secrets.token_urlsafe` generation
- Remove token injection in `serve_index` (no more `__TOKEN_PLACEHOLDER__`)
- Add login router import and registration (unauthenticated)
- `create_token_dependency` still works — it now validates JWT instead of static token

Add import:
```python
from src.planner.api.login import router as login_router
```

Register (unauthenticated):
```python
app.include_router(login_router)
```

Remove or ignore the `auth_token` parameter. The `create_token_dependency` call now returns JWT validation regardless of arguments.

Update `run_server` to not require `auth_token`:
```python
def run_server(db_path: str = None, host: str = "127.0.0.1", port: int = 8321):
    import uvicorn
    app = create_app(db_path=db_path)
    uvicorn.run(app, host=host, port=port, log_level="warning")
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/planner/test_jwt_auth.py -v`
Expected: All 6 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/planner/api/login.py src/planner/api/auth_middleware.py src/planner/server.py tests/planner/test_jwt_auth.py
git commit -m "feat: replace static bearer token with JWT password authentication"
```

---

## Task 3: Frontend Login Page + JWT Storage

**Files:**
- Create: `frontend/src/components/LoginPage.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/index.html`

- [ ] **Step 1: Update API client to use localStorage JWT**

Replace `frontend/src/api/client.ts`:
```typescript
const getToken = (): string => {
  return localStorage.getItem('planner_token') || ''
}

export function setToken(token: string) {
  localStorage.setItem('planner_token', token)
}

export function clearToken() {
  localStorage.removeItem('planner_token')
}

export function hasToken(): boolean {
  return !!localStorage.getItem('planner_token')
}

const BASE = ''

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...options?.headers as Record<string, string>,
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const resp = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
  })

  if (resp.status === 401) {
    clearToken()
    window.location.reload()
    throw new Error('Unauthorized')
  }

  if (!resp.ok) {
    throw new Error(`API error: ${resp.status} ${resp.statusText}`)
  }
  return resp.json()
}
```

- [ ] **Step 2: Create LoginPage component**

Create `frontend/src/components/LoginPage.tsx`:
```tsx
import { useState } from 'react'
import { setToken } from '../api/client'

interface LoginPageProps {
  onLogin: () => void
}

export default function LoginPage({ onLogin }: LoginPageProps) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const resp = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      if (!resp.ok) {
        setError('Invalid password')
        return
      }
      const data = await resp.json()
      setToken(data.token)
      onLogin()
    } catch {
      setError('Connection failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-cream flex items-center justify-center font-body">
      <div className="bg-surface rounded-2xl shadow-card border border-border p-8 w-full max-w-sm">
        <h1 className="font-display font-bold text-2xl text-primary text-center mb-2">
          Planner
        </h1>
        <p className="text-secondary text-sm text-center mb-6">Sign in to your schedule</p>

        <form onSubmit={handleSubmit}>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            autoFocus
            className="w-full bg-cream border border-border rounded-xl px-4 py-3 text-primary placeholder-muted focus:border-accent focus:ring-1 focus:ring-accent/20 focus:outline-none mb-4"
          />
          {error && <p className="text-urgent text-sm mb-3">{error}</p>}
          <button
            type="submit"
            disabled={loading || !password}
            className="w-full py-3 bg-accent hover:bg-accent-hover rounded-xl text-white font-medium disabled:opacity-50 transition-colors"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Update App.tsx with login gate**

In `frontend/src/App.tsx`, add login state:
```tsx
import { useState } from 'react'
import { hasToken } from './api/client'
import LoginPage from './components/LoginPage'

// At the top of App component:
const [loggedIn, setLoggedIn] = useState(hasToken())

if (!loggedIn) {
  return <LoginPage onLogin={() => setLoggedIn(true)} />
}

// ... rest of App
```

- [ ] **Step 4: Remove token placeholder from index.html**

In `frontend/index.html`, remove the line:
```html
<script>window.__PLANNER_TOKEN__ = "__TOKEN_PLACEHOLDER__";</script>
```

- [ ] **Step 5: Build frontend**

Run: `cd frontend && npm run build`

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): add login page with JWT auth, remove static token"
```

---

## Task 4: Push Subscriptions DB + API

**Files:**
- Modify: `src/planner/db.py`
- Create: `src/planner/api/push.py`
- Modify: `src/planner/server.py`
- Create: `tests/planner/test_push.py`

- [ ] **Step 1: Write failing tests**

Create `tests/planner/test_push.py`:
```python
import os
import tempfile
import pytest

os.environ.setdefault("PLANNER_PASSWORD", "testpass123")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-key")

from src.planner.db import PlannerDB
from fastapi.testclient import TestClient
from src.planner.server import create_app


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


@pytest.fixture
def client(db_path):
    app = create_app(db_path=db_path)
    with TestClient(app) as c:
        yield c


def get_token(client):
    resp = client.post("/auth/login", json={"password": "testpass123"})
    return resp.json()["token"]


class TestPushSubscriptionDB:
    def test_add_subscription(self, db):
        sid = db.add_push_subscription("https://endpoint.example.com", "p256dh-key", "auth-key")
        assert sid > 0

    def test_list_subscriptions(self, db):
        db.add_push_subscription("https://endpoint1.com", "key1", "auth1")
        db.add_push_subscription("https://endpoint2.com", "key2", "auth2")
        subs = db.get_push_subscriptions()
        assert len(subs) == 2

    def test_duplicate_endpoint_updates(self, db):
        db.add_push_subscription("https://endpoint.com", "key1", "auth1")
        db.add_push_subscription("https://endpoint.com", "key2", "auth2")
        subs = db.get_push_subscriptions()
        assert len(subs) == 1
        assert subs[0]["p256dh"] == "key2"

    def test_remove_subscription(self, db):
        db.add_push_subscription("https://endpoint.com", "key", "auth")
        db.remove_push_subscription("https://endpoint.com")
        assert db.get_push_subscriptions() == []


class TestPushAPI:
    def test_get_vapid_key(self, client):
        token = get_token(client)
        resp = client.get("/api/push/vapid-key", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "public_key" in resp.json()

    def test_subscribe(self, client):
        token = get_token(client)
        resp = client.post("/api/push/subscribe", json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/test",
            "keys": {"p256dh": "test-key", "auth": "test-auth"},
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
```

- [ ] **Step 2: Add push_subscriptions table and CRUD to db.py**

Add to SCHEMA_SQL:
```sql
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL UNIQUE,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Add methods:
```python
# --- Push Subscriptions ---

def add_push_subscription(self, endpoint: str, p256dh: str, auth: str) -> int:
    conn = self._get_conn()
    cursor = conn.execute(
        "SELECT id FROM push_subscriptions WHERE endpoint = ?", (endpoint,)
    )
    row = cursor.fetchone()
    if row:
        conn.execute(
            "UPDATE push_subscriptions SET p256dh=?, auth=? WHERE id=?",
            (p256dh, auth, row[0]),
        )
        conn.commit()
        return row[0]
    cursor = conn.execute(
        "INSERT INTO push_subscriptions (endpoint, p256dh, auth) VALUES (?, ?, ?)",
        (endpoint, p256dh, auth),
    )
    conn.commit()
    return cursor.lastrowid

def get_push_subscriptions(self) -> list[dict]:
    conn = self._get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT * FROM push_subscriptions")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.row_factory = None
    return rows

def remove_push_subscription(self, endpoint: str) -> None:
    conn = self._get_conn()
    conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
    conn.commit()
```

- [ ] **Step 3: Create push API**

Create `src/planner/api/push.py`:
```python
import os
import json
from fastapi import APIRouter, Depends
from src.planner.db import PlannerDB

router = APIRouter(prefix="/api/push")

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


@router.get("/vapid-key")
def get_vapid_key():
    return {"public_key": VAPID_PUBLIC_KEY}


@router.post("/subscribe")
def subscribe(body: dict, db: PlannerDB = Depends(get_db)):
    endpoint = body.get("endpoint", "")
    keys = body.get("keys", {})
    p256dh = keys.get("p256dh", "")
    auth = keys.get("auth", "")
    if not endpoint or not p256dh or not auth:
        return {"error": "Invalid subscription"}
    db.add_push_subscription(endpoint, p256dh, auth)
    return {"status": "subscribed"}


@router.delete("/subscribe")
def unsubscribe(body: dict, db: PlannerDB = Depends(get_db)):
    endpoint = body.get("endpoint", "")
    db.remove_push_subscription(endpoint)
    return {"status": "unsubscribed"}
```

- [ ] **Step 4: Register in server.py**

Add import and register push routes with auth.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/planner/test_push.py -v`

- [ ] **Step 6: Commit**

```bash
git add src/planner/db.py src/planner/api/push.py src/planner/server.py tests/planner/test_push.py
git commit -m "feat: add Web Push subscription API with VAPID keys"
```

---

## Task 5: Web Push Dispatch in Reminder Service

**Files:**
- Modify: `src/planner/reminders/notifier.py`
- Modify: `src/planner/reminders/service.py`
- Modify: `src/planner/server.py`

- [ ] **Step 1: Add web push to Notifier**

In `src/planner/reminders/notifier.py`, add a method:
```python
def send_web_push(self, title: str, message: str, subscriptions: list[dict]) -> None:
    """Send push notification to all subscribed devices."""
    import os
    from pywebpush import webpush, WebPushException

    vapid_private = os.environ.get("VAPID_PRIVATE_KEY", "")
    vapid_email = os.environ.get("VAPID_EMAIL", "mailto:you@example.com")

    if not vapid_private:
        return

    import json
    payload = json.dumps({"title": title, "body": message, "url": "/"})

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=payload,
                vapid_private_key=vapid_private,
                vapid_claims={"sub": vapid_email},
            )
        except WebPushException as e:
            logger.warning("Web push failed for %s: %s", sub["endpoint"][:50], e)
        except Exception as e:
            logger.warning("Web push error: %s", e)
```

- [ ] **Step 2: Update ReminderService to send web pushes**

In `src/planner/reminders/service.py`, update `check_and_fire` to also send web push:

After firing via `self._notifier.send(...)`, add:
```python
# Send web push to all subscribed devices
subscriptions = self._db.get_push_subscriptions()
if subscriptions:
    self._notifier.send_web_push(title, reminder["message"], subscriptions)
```

- [ ] **Step 3: Commit**

```bash
git add src/planner/reminders/notifier.py src/planner/reminders/service.py
git commit -m "feat: send Web Push notifications when reminders fire"
```

---

## Task 6: PWA — Manifest + Service Worker

**Files:**
- Create: `frontend/public/manifest.json`
- Create: `frontend/public/sw.js`
- Create: `frontend/public/icons/` (generated icons)
- Modify: `frontend/index.html`

- [ ] **Step 1: Create manifest.json**

Create `frontend/public/manifest.json`:
```json
{
  "name": "Productivity Planner",
  "short_name": "Planner",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#EEECE8",
  "theme_color": "#5B5DF0",
  "icons": [
    {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png"}
  ]
}
```

- [ ] **Step 2: Create service worker**

Create `frontend/public/sw.js`:
```javascript
const CACHE_NAME = 'planner-v1'

self.addEventListener('install', (event) => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim())
})

self.addEventListener('fetch', (event) => {
  // Network-first for API calls, cache-first for static assets
  if (event.request.url.includes('/api/') || event.request.url.includes('/auth/')) {
    return // Let browser handle API requests normally
  }
})

// Handle push notifications
self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {}
  const title = data.title || 'Planner'
  const options = {
    body: data.body || '',
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    data: { url: data.url || '/' },
  }
  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url || '/'
  event.waitUntil(clients.openWindow(url))
})
```

- [ ] **Step 3: Generate PWA icons**

Generate simple icons using Python:
```python
from PIL import Image, ImageDraw
import os

os.makedirs("frontend/public/icons", exist_ok=True)

for size in [192, 512]:
    img = Image.new("RGBA", (size, size), "#5B5DF0")
    draw = ImageDraw.Draw(img)
    # White "P" in center
    font_size = size // 2
    draw.text((size*0.3, size*0.2), "P", fill="white")
    img.save(f"frontend/public/icons/icon-{size}.png")
```

- [ ] **Step 4: Update index.html with PWA tags**

In `frontend/index.html`, add to `<head>`:
```html
<link rel="manifest" href="/manifest.json">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="Planner">
<link rel="apple-touch-icon" href="/icons/icon-192.png">
<meta name="theme-color" content="#5B5DF0">
```

Add service worker registration before closing `</body>`:
```html
<script>
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js')
  }
</script>
```

- [ ] **Step 5: Configure Vite to copy public files**

The `frontend/public/` directory is automatically copied to `dist/` by Vite. Verify by building.

- [ ] **Step 6: Build and commit**

```bash
cd frontend && npm run build
git add frontend/
git commit -m "feat: add PWA manifest, service worker, and push notification support"
```

---

## Task 7: Frontend Push Subscription

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add push subscription logic**

In `frontend/src/App.tsx`, add a function that runs after login:
```tsx
async function subscribeToPush() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return
  try {
    const reg = await navigator.serviceWorker.ready
    const vapidResp = await apiFetch<{ public_key: string }>('/api/push/vapid-key')
    if (!vapidResp.public_key) return

    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: vapidResp.public_key,
    })
    const subJson = sub.toJSON()
    await apiFetch('/api/push/subscribe', {
      method: 'POST',
      body: JSON.stringify({
        endpoint: subJson.endpoint,
        keys: subJson.keys,
      }),
    })
  } catch (err) {
    console.log('Push subscription failed:', err)
  }
}
```

Call it in `useEffect` after login:
```tsx
useEffect(() => {
  if (loggedIn) {
    subscribeToPush()
  }
}, [loggedIn])
```

- [ ] **Step 2: Build and commit**

```bash
cd frontend && npm run build
git add frontend/
git commit -m "feat(frontend): auto-subscribe to push notifications after login"
```

---

## Task 8: Canvas Scraping via Requests (No Playwright)

**Files:**
- Create: `src/planner/ingestion/canvas_requests.py`
- Modify: `src/planner/server.py`
- Modify: `frontend/src/components/SettingsView.tsx`
- Create: `tests/planner/test_canvas_requests.py`

- [ ] **Step 1: Create requests-based Canvas scraper**

Create `src/planner/ingestion/canvas_requests.py`:
```python
import json
import logging
import requests
from datetime import datetime, timezone

from src.planner.db import PlannerDB
from src.planner.encryption import EncryptionManager
from src.planner.ingestion.canvas_parser import CanvasParser

logger = logging.getLogger(__name__)


class CanvasRequestsScraper:
    """Scrape Canvas using requests + stored cookies (no Playwright)."""

    def __init__(self, db: PlannerDB, encryption: EncryptionManager):
        self._db = db
        self._encryption = encryption

    def sync_config(self, config_id: int) -> int:
        config = self._db.get_canvas_config(config_id)
        if not config or config["status"] != "active":
            return 0

        canvas_url = config["canvas_url"].rstrip("/")
        try:
            cookies_raw = self._encryption.decrypt(config["session_cookies"])
            cookies_list = json.loads(cookies_raw)
        except Exception:
            logger.error("Failed to decrypt cookies for config %d", config_id)
            self._db.update_canvas_status(config_id, "error")
            return 0

        session = requests.Session()
        # Convert cookie list to requests cookies
        for cookie in cookies_list:
            session.cookies.set(
                cookie.get("name", ""),
                cookie.get("value", ""),
                domain=cookie.get("domain", ""),
                path=cookie.get("path", "/"),
            )

        # Verify session by checking courses page
        resp = session.get(f"{canvas_url}/courses", allow_redirects=False, timeout=30)
        if resp.status_code in (301, 302, 303) and "login" in resp.headers.get("Location", "").lower():
            self._db.update_canvas_status(config_id, "expired")
            logger.warning("Canvas session expired for config %d", config_id)
            return 0

        parser = CanvasParser(canvas_url)
        total = 0

        # Extract courses
        courses_html = resp.text if resp.status_code == 200 else ""
        courses = parser.extract_course_list(courses_html)

        # Filter to current semester
        current_markers = ["sp26", "spring 2026", "spr26"]
        filtered = [c for c in courses if any(m in c["name"].lower() for m in current_markers)]
        if filtered:
            courses = filtered

        for course in courses:
            course_id = course["id"]
            course_name = course["name"]

            import re
            code_match = re.search(r'-\s*(.+?)(?:\s*\(\d+\))?$', course_name)
            course_code = code_match.group(1).strip() if code_match else course_name

            # Scrape assignments
            try:
                resp = session.get(f"{canvas_url}/courses/{course_id}/assignments", timeout=30)
                if resp.status_code == 200:
                    assignments = parser.parse_assignments_page(resp.text, course_id, course_name)
                    for a in assignments:
                        self._db.upsert_task(
                            source="canvas", external_id=a["external_id"],
                            title=a["title"], course=a["course"], deadline=a.get("due_date"),
                        )
                        total += 1
            except Exception as e:
                logger.warning("Failed assignments for %s: %s", course_name, e)

            # Scrape grades
            try:
                resp = session.get(f"{canvas_url}/courses/{course_id}/grades", timeout=30)
                if resp.status_code == 200:
                    grade_info = parser.parse_grades_page(resp.text, course_id)
                    # Save course
                    self._db.upsert_course(
                        canvas_course_id=course_id, name=course_name, code=course_code,
                        canvas_config_id=config_id,
                    )
                    if grade_info["current_grade"]:
                        conn = self._db._get_conn()
                        cursor = conn.execute("SELECT id FROM courses WHERE canvas_course_id = ?", (course_id,))
                        row = cursor.fetchone()
                        if row:
                            self._db.update_course_grade(row[0], grade_info["current_grade"])
            except Exception as e:
                logger.warning("Failed grades for %s: %s", course_name, e)

        now = datetime.now(timezone.utc).isoformat()
        self._db.update_canvas_last_sync(config_id, now)
        return total
```

- [ ] **Step 2: Add cookie paste endpoint to canvas API**

In `src/planner/api/canvas.py`, add:
```python
@router.post("/cookies/{config_id}")
def paste_cookies(config_id: int, body: dict, db: PlannerDB = Depends(get_db)):
    """Update Canvas cookies from browser paste."""
    cookies_json = body.get("cookies", "")
    if not cookies_json:
        return {"error": "No cookies provided"}
    try:
        # Validate it's valid JSON
        cookies = json.loads(cookies_json) if isinstance(cookies_json, str) else cookies_json
        from src.planner.encryption import EncryptionManager
        encryption = EncryptionManager()
        encrypted = encryption.encrypt(json.dumps(cookies))
        db.update_canvas_cookies(config_id, encrypted)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}
```

Add `import json` at top if not already imported.

- [ ] **Step 3: Update server.py to use requests scraper**

Replace `CanvasScraper` import with `CanvasRequestsScraper` and use it for the sync scheduler and canvas module.

- [ ] **Step 4: Add cookie paste to Settings UI**

In `frontend/src/components/SettingsView.tsx`, in the CanvasPanel section, add a textarea for pasting cookies.

- [ ] **Step 5: Build and commit**

```bash
cd frontend && npm run build
git add src/planner/ingestion/canvas_requests.py src/planner/api/canvas.py src/planner/server.py frontend/
git commit -m "feat: replace Playwright Canvas scraper with requests-based cookie paste"
```

---

## Task 9: Docker + Deployment Files

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `run_server.py`
- Create: `nginx/planner.conf`
- Create: `deploy.sh`

- [ ] **Step 1: Create Gunicorn entry point**

Create `run_server.py`:
```python
from src.planner.server import create_app

app = create_app()
```

- [ ] **Step 2: Create Dockerfile**

Create `Dockerfile`:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application code
COPY src/ src/
COPY frontend/dist/ frontend/dist/
COPY run_server.py .

# Data directory
RUN mkdir -p /app/data

ENV PYTHONPATH=/app

EXPOSE 8321

CMD ["gunicorn", "run_server:app", \
     "-w", "2", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8321", \
     "--timeout", "300"]
```

- [ ] **Step 3: Create docker-compose.yml**

Create `docker-compose.yml`:
```yaml
version: "3.8"

services:
  planner:
    build: .
    ports:
      - "8321:8321"
    volumes:
      - planner_data:/app/data
    environment:
      - PLANNER_PASSWORD=${PLANNER_PASSWORD}
      - JWT_SECRET=${JWT_SECRET}
      - VAPID_PRIVATE_KEY=${VAPID_PRIVATE_KEY}
      - VAPID_PUBLIC_KEY=${VAPID_PUBLIC_KEY}
      - VAPID_EMAIL=${VAPID_EMAIL}
    restart: unless-stopped

volumes:
  planner_data:
```

- [ ] **Step 4: Create Nginx config**

Create `nginx/planner.conf`:
```nginx
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name _;

    ssl_certificate /etc/letsencrypt/live/DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/DOMAIN/privkey.pem;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8321;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE streaming
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

- [ ] **Step 5: Create deployment script**

Create `deploy.sh`:
```bash
#!/bin/bash
# Run on the VPS after first SSH login
# Usage: bash deploy.sh yourdomain.com

DOMAIN=$1
if [ -z "$DOMAIN" ]; then
    echo "Usage: bash deploy.sh yourdomain.com"
    exit 1
fi

# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Nginx + Certbot
apt-get update && apt-get install -y nginx certbot python3-certbot-nginx

# Get SSL cert
certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN

# Replace domain in nginx config
sed -i "s/DOMAIN/$DOMAIN/g" nginx/planner.conf
cp nginx/planner.conf /etc/nginx/sites-available/planner
ln -sf /etc/nginx/sites-available/planner /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# Generate VAPID keys
python3 -c "
from pywebpush import webpush
import json
keys = webpush.generate_vapid_keys()
# Actually use py_vapid
from py_vapid import Vapid
v = Vapid()
v.generate_keys()
print('VAPID_PRIVATE_KEY=' + v.private_pem())
print('VAPID_PUBLIC_KEY=' + v.public_key_urlsafe())
"

echo ""
echo "=== Setup Complete ==="
echo "1. Create .env file with: PLANNER_PASSWORD, JWT_SECRET, VAPID keys"
echo "2. Run: docker compose up -d"
echo "3. Access at: https://$DOMAIN"
```

- [ ] **Step 6: Create .env.example**

Create `.env.example`:
```
PLANNER_PASSWORD=your-secure-password-here
JWT_SECRET=generate-a-random-string-here
VAPID_PRIVATE_KEY=your-vapid-private-key
VAPID_PUBLIC_KEY=your-vapid-public-key
VAPID_EMAIL=mailto:you@example.com
```

- [ ] **Step 7: Commit**

```bash
git add Dockerfile docker-compose.yml run_server.py nginx/ deploy.sh .env.example
git commit -m "feat: add Docker, Nginx, and deployment configuration"
```

---

## Task 10: Run All Tests + Final Build

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/planner/ -v`
Expected: All tests pass

- [ ] **Step 2: Build frontend**

Run: `cd frontend && npm run build`

- [ ] **Step 3: Test Docker build locally**

Run: `docker build -t planner .`
Expected: Build succeeds

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final build for Hetzner deployment"
```
