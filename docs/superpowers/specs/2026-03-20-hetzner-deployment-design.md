# Hetzner VPS Deployment — Design Specification

**Date:** 2026-03-20
**Status:** Draft
**Scope:** Deploy existing AI scheduling planner to Hetzner VPS with multi-device access, PWA, and push notifications

---

## 1. Overview

Deploy the existing FastAPI + React planner to a Hetzner CX22 VPS (€3.29/mo) so it's accessible from iPhone, MacBook, and PC. Add password authentication, Progressive Web App support for phone install, and Web Push notifications for cross-device reminders.

### Goals
- Access planner from any device via HTTPS
- PWA install on iPhone (looks like native app)
- Push notifications on all devices for reminders/alerts
- Canvas scraping without Playwright (cookie paste + requests)
- Single Docker container deployment

### Non-Goals
- Multi-user support
- Native mobile apps
- Playwright on the server

---

## 2. Architecture

```
Devices (iPhone, MacBook, PC)
        │ HTTPS
        ▼
   Hetzner CX22 VPS (€3.29/mo)
   │   2 vCPU, 4GB RAM, 40GB disk, Ubuntu
   │
   ├── Nginx (reverse proxy)
   │   └── Let's Encrypt SSL (Certbot, auto-renew)
   │
   ├── Docker Container
   │   ├── Gunicorn + Uvicorn workers (FastAPI)
   │   ├── SQLite database (Docker volume)
   │   ├── APScheduler (Gmail/GCal sync, Canvas scrape, reminders)
   │   ├── Web Push service (pywebpush + VAPID)
   │   └── React PWA (static files served by FastAPI)
   │
   └── Domain (cheap or free DuckDNS subdomain)
```

---

## 3. Authentication

### Password Login
- Single-user app — one password set via environment variable `PLANNER_PASSWORD`
- Login page: simple form, POST `/auth/login` with password
- Returns a JWT token (HS256, signed with `JWT_SECRET` env var)
- Token stored in `localStorage`, sent as `Authorization: Bearer <jwt>` header
- Token expires after 30 days (long-lived since single user)
- All API routes validate JWT instead of the current static bearer token

### Migration from Static Token
- Remove the current `auth_token` parameter from `create_app`
- Replace `create_token_dependency` with JWT validation
- The `/health` endpoint remains unauthenticated
- OAuth callback (`/auth/callback`) remains unauthenticated

---

## 4. Progressive Web App (PWA)

### manifest.json
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

### Service Worker
- Cache-first for static assets (JS, CSS, fonts, icons)
- Network-first for API calls
- Enables "Add to Home Screen" on iOS Safari
- Minimal — just enough for PWA install eligibility

### iOS Requirements
- Must be served over HTTPS
- User must "Add to Home Screen" from Safari
- `manifest.json` must have proper icons
- `apple-mobile-web-app-capable` meta tag

---

## 5. Web Push Notifications

### VAPID Keys
- Generated once during setup (`pywebpush.generate_vapid_keys()`)
- Public key served via `GET /api/push/vapid-key`
- Private key stored in environment variable `VAPID_PRIVATE_KEY`

### Frontend Subscription Flow
1. After login, frontend requests notification permission
2. If granted, subscribes via `serviceWorkerRegistration.pushManager.subscribe()`
3. Sends subscription object to `POST /api/push/subscribe`
4. Backend stores subscription in new `push_subscriptions` table

### Backend Push Dispatch
- When the reminder service fires a reminder, also send a Web Push
- `pywebpush.webpush(subscription, payload, vapid_claims)`
- Payload: `{"title": "Reminder", "body": "Time to start: Calculus", "url": "/"}`
- Service worker receives push event and shows native notification

### Push Subscription Table
```sql
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL UNIQUE,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Platform Support
- macOS Chrome/Safari: works natively
- iOS Safari: works when PWA is installed (iOS 16.4+)
- Android Chrome: works natively

---

## 6. Canvas Scraping — Cookie Paste

### Approach
- No Playwright anywhere — replace with `requests` + stored cookies
- Settings page gets a "Canvas Cookies" textarea field
- User workflow when cookies expire:
  1. Open Canvas in browser, log in
  2. Use browser DevTools (Application → Cookies) or a cookie export extension
  3. Copy cookies as JSON
  4. Paste into planner Settings → Canvas Cookies field
- Backend stores encrypted cookies (existing Fernet encryption)

### Scraping with requests
- Replace Playwright-based scraper with `requests.Session`
- Load cookies into session: `session.cookies.update(cookie_dict)`
- Fetch Canvas pages: `session.get(f"{canvas_url}/courses/{id}/assignments")`
- Parse HTML with existing `CanvasParser` (unchanged)
- Session expiry detection: check for redirect to login page (HTTP 302 to SSO)

---

## 7. Docker Setup

### Dockerfile
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY src/ src/
COPY frontend/dist/ frontend/dist/
COPY run_server.py .
EXPOSE 8321
CMD ["gunicorn", "run_server:app", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8321"]
```

Note: Python 3.12 (not 3.14) for maximum compatibility.

### docker-compose.yml
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
    restart: unless-stopped

volumes:
  planner_data:
```

### Data Persistence
- SQLite database stored in Docker volume `planner_data`
- Mapped to `/app/data/planner.db` inside container
- Survives container rebuilds/restarts
- `google_client_config.json` also in the data volume

---

## 8. VPS Setup (Hetzner CX22)

### Server Provisioning
- Ubuntu 24.04 LTS
- SSH key authentication (no password SSH)
- UFW firewall: allow 22 (SSH), 80 (HTTP), 443 (HTTPS)

### Nginx Configuration
```nginx
server {
    listen 80;
    server_name planner.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name planner.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/planner.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/planner.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8321;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE streaming support
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

### SSL
- Let's Encrypt via Certbot
- Auto-renewal via systemd timer (default with Certbot)

### Domain Options
- Cheap domain: ~$1/yr from Cloudflare/Namecheap (.xyz, .site)
- Free: DuckDNS subdomain (yourname.duckdns.org)

---

## 9. Deployment Workflow

### Initial Setup (one-time)
1. Create Hetzner CX22 VPS
2. SSH in, install Docker + Nginx + Certbot
3. Set up domain DNS → VPS IP
4. Get SSL certificate
5. Clone repo, create `.env` file with secrets
6. `docker compose up -d`

### Updating
```bash
ssh vps
cd ~/productivity
git pull
docker compose build && docker compose up -d
```

### Monitoring
- `docker compose logs -f` for logs
- Gunicorn auto-restarts workers on crash

---

## 10. File Changes Summary

### New Files
| File | Purpose |
|------|---------|
| `Dockerfile` | Container image definition |
| `docker-compose.yml` | Service orchestration |
| `run_server.py` | Gunicorn entry point |
| `nginx/planner.conf` | Nginx reverse proxy config |
| `frontend/public/manifest.json` | PWA manifest |
| `frontend/public/sw.js` | Service worker |
| `frontend/public/icons/` | PWA icons (192, 512) |
| `src/planner/api/push.py` | Web Push subscription + dispatch |
| `src/planner/api/login.py` | Password login + JWT |
| `src/planner/ingestion/canvas_requests.py` | Canvas scraping via requests (no Playwright) |
| `scripts/canvas_sync_local.py` | (removed — not needed with cookie paste) |

### Modified Files
| File | Change |
|------|--------|
| `src/planner/server.py` | JWT auth, push routes, remove static token |
| `src/planner/api/auth_middleware.py` | JWT validation instead of static token |
| `src/planner/db.py` | Add push_subscriptions table |
| `src/planner/reminders/service.py` | Send Web Push alongside system notifications |
| `frontend/index.html` | PWA meta tags, manifest link, service worker registration |
| `frontend/src/App.tsx` | Login page, push subscription prompt |
| `frontend/src/components/SettingsView.tsx` | Canvas cookie paste textarea |
| `requirements.txt` | Add PyJWT, pywebpush, gunicorn; remove playwright |
