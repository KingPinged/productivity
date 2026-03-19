# AI Scheduling Assistant & Daily Planner — Design Specification

**Date:** 2026-03-19
**Status:** Draft
**Scope:** New subsystem added to the existing productivity app

---

## 1. Overview

An AI-powered scheduling assistant that aggregates data from multiple sources (Gmail, Google Calendar, Canvas LMS, app/website usage patterns), uses Claude API to autonomously plan the user's day, and presents it in a modern calendar/to-do UI via an embedded webview. The system dynamically replans based on changing events, completed tasks, and energy/rest needs.

### Goals
- Aggregate all scheduling-relevant data into a single view
- Autonomously generate and maintain a time-blocked daily schedule
- Account for workload, deadlines, grades, energy levels, and rest
- Provide reminders with sound and system notifications
- Replace the pomodoro timer as the primary time management system (pomodoro becomes optional)

### Non-Goals (for v1)
- Writing back to Google Calendar (read-only)
- Mobile app or remote access
- Multi-user / collaboration features
- Integration with non-Google email providers

---

## 2. System Architecture

### High-Level Components

```
Existing Tkinter App (orchestrator)
  ├── Pomodoro timer, blocking, usage tracking (unchanged)
  ├── Launches FastAPI backend service (new, subprocess)
  │     ├── Data ingestion pipeline (Gmail, GCal, Canvas, usage)
  │     ├── AI scheduling engine (Claude API)
  │     ├── Reminder service
  │     └── SQLite database
  └── Launches pywebview window (new)
        └── React app consuming FastAPI endpoints
```

### Process Model
- **Existing Tkinter app** remains the primary process and orchestrator
- **FastAPI backend** runs as a subprocess on `127.0.0.1:8321` (localhost only, not `0.0.0.0`)
- **React frontend** is pre-built and bundled as static files served by FastAPI, displayed in a pywebview window
- Communication between Tkinter app and FastAPI via local HTTP, authenticated with a per-session bearer token

### API Security
- On startup, the Tkinter app generates a cryptographically random bearer token (32 bytes, `secrets.token_urlsafe()`)
- Token is passed to the FastAPI subprocess via environment variable
- All FastAPI endpoints require `Authorization: Bearer <token>` header
- Token is injected into the React app config at serve time
- CORS restricted to pywebview origin only
- Server binds exclusively to `127.0.0.1` (not accessible from network)

### Subprocess Lifecycle
- **Startup:** Tkinter launches FastAPI subprocess, polls `GET /health` until ready (timeout 10s, then retry or show error)
- **Health check:** FastAPI exposes `GET /health` (unauthenticated) returning `{"status": "ok"}`
- **Shutdown:** Tkinter sends SIGTERM (Unix) or calls `terminate()` (Windows) on exit; FastAPI registers `atexit` handler for cleanup
- **Crash recovery:** Tkinter monitors subprocess; if it dies, restarts automatically (max 3 restarts, then shows error to user)
- **Port conflict:** If port 8321 is in use, tries ports 8322-8325 sequentially; selected port communicated to pywebview

### Integration with Existing App
- Tray icon gets a new menu item: "Open Planner"
- FastAPI reads usage data from the existing app via a local HTTP endpoint on the Tkinter app's extension server (`127.0.0.1:52525/usage`), avoiding file locking issues with direct `usage_data.json` reads
- When "AI time management" is enabled, the pomodoro timer becomes optional — AI schedule blocks replace it
- Blocking, NSFW detection, and usage tracking continue to operate independently

---

## 3. Data Ingestion Pipeline

### 3.1 Gmail Integration (OAuth 2.0)

**Authentication:**
- User adds Gmail accounts via Settings in the planner UI
- OAuth 2.0 flow opens browser for Google consent (scopes: `gmail.readonly`, `calendar.readonly`)
- Redirect to `localhost:8321/auth/callback` captures tokens
- OAuth flow must include a `state` parameter (random nonce) validated on callback to prevent CSRF
- Tokens stored in OS credential store (Windows Credential Manager via `keyring` library, macOS Keychain)
- Refresh tokens handle automatic re-authentication
- Supports 3+ accounts (personal, school, work)

**Data Extraction:**
- Scans inbox and starred emails (skips promotions/spam/social)
- Claude parses recent emails to identify action items, deadlines, and date references
- Calendar invites received via email are extracted

**Sync Frequency:**
- Every 15 minutes for new emails
- Daily deep scan of unread/starred

### 3.2 Google Calendar Integration (same OAuth flow)

**Data Extraction:**
- Pulls all calendars per authenticated account (personal, school, shared)
- Extracts: events, recurring events, all-day events, event descriptions
- Read-only — AI displays events on its own calendar but does not write back to Google Calendar

**Sync Frequency:** Every 15 minutes

### 3.3 Canvas LMS Scraping (Playwright)

**Authentication:**
- User provides Canvas URL (e.g., `canvas.university.edu`)
- Playwright opens a headed browser window for initial manual login (handles SSO/MFA)
- Session cookies saved and reused for subsequent headless scrapes

**Data Extraction:**
- Dashboard: upcoming assignments with due dates
- Course pages: syllabus dates, exam schedules
- Calendar page: all Canvas calendar events
- Grades page: current grades per course (used for AI prioritization — lower grades get more study time)

**Sync Frequency:** Every 2 hours (Canvas data changes slowly). Manual force-refresh available.

**Resilience:**
- Session expiry detected by: HTTP 401/403 responses, redirect to SSO login page, expected DOM elements missing from scraped pages
- On expiry: in-app banner notification in the planner UI + system notification prompting re-login
- Retry logic: max 2 retries with 30s delay before marking session as expired
- Graceful failure — missing Canvas data doesn't break the system; schedule continues with existing cached data
- Distinguishes transient errors (network timeout → retry silently) from auth errors (SSO redirect → notify user)

### 3.4 App/Website Usage Patterns (Existing Data)

- Fetches usage data from the existing app's extension server (`127.0.0.1:52525/usage`) to avoid file locking conflicts
- Extracts: daily usage patterns, most productive hours, time spent per app/site
- Used by AI to understand when the user works best and schedule accordingly
- Usage data path is platform-aware: resolved via the same constants module used by the existing app, or passed as a config parameter when launching the FastAPI subprocess

---

## 4. AI Scheduling Engine (Claude API)

### 4.1 Core Behavior

The AI engine autonomously generates and maintains a time-blocked daily schedule.

**Daily Planning Cycle:**
1. **Morning generation:** Triggered at configurable wake time or on first app open. Claude receives all current data and generates the full day's schedule.
2. **Continuous replanning:** When data materially changes (new email, completed task, missed block), the engine replans the remainder of the day.
3. **7-day look-ahead:** Today's plan accounts for upcoming deadlines in the next 7-14 days.

### 4.2 Context Provided to Claude

```
- Today's date, day of week
- All calendar events (next 7 days)
- All assignments/deadlines (next 14 days)
- Gmail action items (pending)
- Current grades per course (from Canvas)
- Usage patterns: avg productive hours/day, peak hours, break patterns
- User preferences: wake time, sleep time, max work hours, break preferences
- What's been completed today so far
- Current task list with priorities
```

### 4.3 Structured Output from Claude

```json
{
  "schedule": [
    {
      "start": "09:00",
      "end": "10:30",
      "task": "Calculus Problem Set 4",
      "type": "study",
      "priority": "high",
      "reason": "Due tomorrow, grade is B-"
    },
    {
      "start": "10:30",
      "end": "10:45",
      "task": "Break",
      "type": "rest"
    }
  ],
  "tasks_today": ["Calculus PS4", "CS Lab Report", "Reply to Prof. email"],
  "tasks_later": ["History essay outline (due next week)"],
  "reminders": [
    {"time": "14:00", "message": "Team meeting in 30 min", "urgent": true}
  ]
}
```

### 4.4 Scheduling Intelligence

**Priority reasoning:**
- Urgency (deadline proximity) x importance (grade weight, course grade)
- Lower grades in a course -> more study time allocated
- Higher point-value assignments get more estimated time
- Email action items ranked by sender importance and age

**Rest & energy management:**
- Enforces break blocks (configurable, defaults to 15 min every 90 min)
- No scheduling past user's configured end-of-day time
- Harder subjects scheduled during peak productive hours (learned from usage data)
- Lighter tasks (emails, organizing) in low-energy windows
- Longer rest suggested after heavy study blocks

**Dynamic replanning triggers:**
- Task marked complete -> remaining time redistributed
- New calendar event synced -> schedule adjusts around it
- User hasn't started a block after 10 min -> AI nudges or reschedules
- User manually moves/skips a block in the UI

### 4.5 Error Handling

- **API down / network error:** Keep the last valid schedule as fallback. Show a degraded-mode indicator in the UI ("AI offline — showing last schedule"). Retry with exponential backoff (5s, 15s, 60s, then every 5 min).
- **Malformed JSON:** Validate Claude's output against a JSON schema before accepting. If validation fails, retry once with a repair prompt. If still invalid, keep previous schedule.
- **Schedule conflicts:** Post-process Claude's output to detect overlapping blocks. If found, reject and retry with explicit "no overlaps" instruction.
- **Invalid API key / rate limited:** Surface error in Settings view with clear message. Rate limit → back off per Anthropic retry headers.
- **Stale schedule indicator:** If the schedule is >4 hours old and hasn't been refreshed, show a subtle "last updated X hours ago" badge.

### 4.6 Token Efficiency

- Full replan only when data materially changes
- Minor adjustments handled with smaller prompts
- Schedule template cached — Claude modifies rather than regenerates from scratch
- **Token budget estimate:** Morning full plan ~4,000 input tokens (context) + ~1,500 output tokens. Routine replans ~2,000 input + ~800 output. At ~5-8 replans/day using Sonnet, estimated cost: ~$0.05-0.15/day. Morning Opus plan adds ~$0.10.

---

## 5. Frontend UI (React + pywebview)

### 5.1 Tech Stack
- React with TypeScript
- Tailwind CSS for styling
- FullCalendar library for calendar component (drag-drop support)
- Bundled with Vite, served by FastAPI as static files
- pywebview window (~1200x800, resizable)

### 5.2 Layout

```
+----------+-------------------------------------+
|          |                                     |
| Today    |   [Calendar / Schedule View]        |
| Tasks    |                                     |
| Week     |   Time-blocked day view with        |
| Settings |   color-coded blocks                |
|          |                                     |
|----------+-------------------------------------|
|          |                                     |
| What's   |   Blocks are draggable to           |
| Next:    |   reschedule. Click to mark          |
| ------   |   complete or skip.                  |
| Calc PS4 |                                     |
| due tmrw |                                     |
|          |                                     |
| Later:   |                                     |
| ------   |                                     |
| CS Lab   |                                     |
| History  |                                     |
+----------+-------------------------------------+
```

### 5.3 Views

**Today View (default):**
- Vertical timeline with 30-min grid
- Color-coded blocks: study (blue), meetings (green), rest (amber), personal (purple)
- Current time indicator line
- Click block -> details panel (task info, AI reasoning)
- Drag blocks to reschedule -> triggers AI replan

**Tasks View:**
- Three columns: Now (today's remaining), Later (this week), Future (beyond)
- Each task: title, source icon (Canvas/Gmail/manual), deadline, estimated time, priority badge
- Quick-add bar at top for manual tasks
- Check off tasks -> AI replans remaining day

**Week View:**
- 7-day calendar grid with all events and scheduled blocks
- Overview of upcoming deadlines and workload distribution
- Read-only for manual scheduling — the AI handles future day planning autonomously; manual intervention is only needed for today's schedule where real-time adjustments matter

**Settings View:**
- Account management: add/remove Gmail and Google Calendar accounts
- Canvas configuration: URL, re-login button, sync status per source
- Preferences: wake time, sleep time, max work hours/day, break frequency
- AI behavior: schedule style (packed vs relaxed), preferred study block length
- Notification settings: sound selection, quiet hours

---

## 6. Reminders & Notifications

### 6.1 Reminder Types

| Type | Trigger | Sound | Example |
|------|---------|-------|---------|
| Upcoming event | 30 min + 5 min before | Gentle chime | "Team meeting in 30 minutes" |
| Task start | When schedule block begins | Medium tone | "Time to start: Calculus PS4" |
| Deadline warning | 24h + 3h before due | Urgent tone | "Calculus PS4 due in 3 hours" |
| Break reminder | When rest block starts | Soft bell | "Take a 15 minute break" |
| Nudge | 10 min into block, no activity | Gentle ping | "Haven't started CS Lab — reschedule?" |
| Daily summary | Morning at wake time | Notification only | "4 tasks today. First up: Calculus at 9:00" |

### 6.2 Implementation
- **Windows:** `win10toast` or `plyer` for native toast notifications
- **macOS:** `pyobjc` notification center
- **Sound:** Bundled `.wav` files played via `playsound` or platform-native APIs
- **Quiet hours:** Configurable window where only urgent deadline reminders fire

### 6.3 Nudge System
- AI monitors usage tracker — checks if user is on an unproductive app during a study block (using aggregate productivity status, not specific app names)
- Only aggregate usage patterns (e.g., "productive hours per day", "peak hours") are sent to Claude API for scheduling context — specific app/website names stay local
- After 2 ignored nudges, AI silently reschedules that block to later
- No punishment, just adaptation
- Nudge system is enabled by default but can be toggled off in preferences

---

## 7. Data Model (SQLite)

### Tables

```sql
-- Gmail/GCal accounts (tokens stored in OS credential store, not here)
accounts (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  provider TEXT DEFAULT 'google',
  scopes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_sync TIMESTAMP,
  deleted_at TIMESTAMP              -- soft delete
)

-- Canvas scraping sessions
canvas_configs (
  id INTEGER PRIMARY KEY,
  canvas_url TEXT NOT NULL,
  session_cookies TEXT NOT NULL,    -- Fernet encrypted
  last_sync TIMESTAMP,
  status TEXT DEFAULT 'active'      -- active|expired|error
)

-- Unified events from all sources
events (
  id INTEGER PRIMARY KEY,
  account_id INTEGER REFERENCES accounts(id),
  source TEXT NOT NULL,             -- gcal|gmail|canvas|manual
  external_id TEXT,                 -- dedup key
  title TEXT NOT NULL,
  description TEXT,
  start_time TIMESTAMP,
  end_time TIMESTAMP,
  all_day BOOLEAN DEFAULT FALSE,
  recurring_rule TEXT,
  location TEXT,
  event_type TEXT,                  -- meeting|deadline|exam|class
  raw_data TEXT,                    -- JSON blob
  synced_at TIMESTAMP,
  UNIQUE(source, external_id)
)

-- Tasks extracted or manually created
tasks (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,             -- canvas|gmail|manual
  external_id TEXT,
  title TEXT NOT NULL,
  description TEXT,
  course TEXT,
  deadline TIMESTAMP,
  estimated_minutes INTEGER,
  priority INTEGER DEFAULT 3,      -- 1 (highest) to 5 (lowest)
  status TEXT DEFAULT 'pending',   -- pending|in_progress|done|skipped
  grade_weight REAL,
  current_grade TEXT,
  ai_notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP,
  UNIQUE(source, external_id)
)

-- AI-generated schedule blocks
schedule_blocks (
  id INTEGER PRIMARY KEY,
  task_id INTEGER REFERENCES tasks(id),
  date DATE NOT NULL,
  start_time TEXT NOT NULL,        -- HH:MM
  end_time TEXT NOT NULL,          -- HH:MM
  block_type TEXT NOT NULL,        -- study|meeting|rest|personal|buffer
  status TEXT DEFAULT 'scheduled', -- scheduled|active|completed|skipped|rescheduled
  ai_reason TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)

-- Reminders
reminders (
  id INTEGER PRIMARY KEY,
  schedule_block_id INTEGER REFERENCES schedule_blocks(id),
  task_id INTEGER REFERENCES tasks(id),
  remind_at TIMESTAMP NOT NULL,
  reminder_type TEXT NOT NULL,     -- event|task_start|deadline|break|nudge|summary
  message TEXT NOT NULL,
  urgent BOOLEAN DEFAULT FALSE,
  fired BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)

-- User preferences (key-value)
preferences (
  key TEXT PRIMARY KEY,
  value TEXT                       -- JSON-encoded value
)

-- AI context cache for token efficiency
ai_context_cache (
  id INTEGER PRIMARY KEY,
  date DATE NOT NULL,
  context_hash TEXT,
  schedule_json TEXT,
  tokens_used INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### Encryption & Credential Storage
- OAuth tokens and refresh tokens stored in the OS credential store (Windows Credential Manager via `keyring`, macOS Keychain) — not in SQLite
- Canvas session cookies encrypted at rest using `cryptography.Fernet` in SQLite, with the Fernet key stored in the OS credential store
- The `accounts` table stores email and metadata only; tokens are retrieved from the OS credential store at runtime using `keyring.get_password("productivity-planner", email)`

### Timezone Handling
- All timestamps stored in UTC internally (SQLite TIMESTAMP columns)
- Google Calendar timezone data preserved in `raw_data` JSON and converted to UTC on import
- Canvas deadlines assumed to be in the university's timezone (configurable in preferences)
- Display layer converts UTC to user's local timezone

### Schedule Block / Task Relationships
- Multiple schedule blocks can reference the same task (e.g., studying for an exam split across morning and afternoon)
- When a task is marked complete, all its future schedule blocks are automatically marked as "completed" and their time is reclaimed for replanning
- When a task is deleted, associated future schedule blocks are marked "rescheduled" and removed from the schedule; past completed blocks are preserved for history
- Rest/buffer blocks have `task_id = NULL`

### Account & Data Cleanup
- When an account is removed (`DELETE /auth/accounts/:id`): credentials removed from OS credential store, associated events and tasks are soft-deleted (marked with `deleted_at` timestamp), schedule blocks referencing those tasks are marked "rescheduled"
- `DELETE /canvas/configs/:id` endpoint removes Canvas configuration; associated tasks and events follow the same soft-delete cascade
- Historical schedule data (completed blocks) is preserved for analytics even after account removal

### Deduplication Strategy
- Gmail-sourced tasks: deduplication key is `gmail:<message_id>:<task_index>` where `task_index` is the position of the extracted task within a single email
- Canvas-sourced tasks: deduplication key is `canvas:<course_id>:<assignment_id>`
- Calendar events: deduplication key is `gcal:<calendar_id>:<event_id>`

---

## 8. API Endpoints (FastAPI)

### Authentication
```
GET  /auth/google          -> Initiates OAuth flow (opens browser)
GET  /auth/callback        -> OAuth redirect handler
GET  /auth/accounts        -> List connected accounts
DELETE /auth/accounts/:id  -> Remove account (soft-delete + cascade)
```

### Data Sync
```
POST /sync/trigger         -> Force sync all sources
GET  /sync/status          -> Sync status per source (last sync time, errors)
POST /canvas/setup         -> Configure Canvas URL, launch login browser
POST /canvas/relogin       -> Re-authenticate Canvas session
DELETE /canvas/configs/:id -> Remove Canvas configuration (soft-delete + cascade)
```

### Schedule & Tasks
```
GET  /api/schedule/:date   -> Get schedule blocks for a date
POST /api/schedule/replan  -> Trigger AI replan for today
PATCH /api/schedule/:id    -> Update block (move, complete, skip)

GET  /api/tasks            -> List tasks (filterable by status, source, date range)
POST /api/tasks            -> Create manual task
PATCH /api/tasks/:id       -> Update task (status, priority, estimated time)
DELETE /api/tasks/:id      -> Delete task
```

### Calendar Events
```
GET  /api/events           -> List events (filterable by date range, source)
```

### Reminders
```
GET  /api/reminders        -> List pending reminders
PATCH /api/reminders/:id   -> Dismiss/snooze reminder
```

### Preferences
```
GET  /api/preferences      -> Get all preferences
PATCH /api/preferences     -> Update preferences
```

---

## 9. Project Structure (New Files)

```
src/
  planner/                         # New planner subsystem
    __init__.py
    server.py                      # FastAPI app entry point
    config.py                      # Planner-specific config
    db.py                          # SQLite connection + migrations
    encryption.py                  # Fernet encryption helpers

    ingestion/                     # Data collectors
      __init__.py
      gmail.py                     # Gmail OAuth + email parsing
      gcal.py                      # Google Calendar sync
      canvas.py                    # Playwright Canvas scraper
      usage.py                     # Fetches usage data from extension server HTTP endpoint

    ai/                            # AI scheduling engine
      __init__.py
      scheduler.py                 # Core scheduling logic + Claude API
      context_builder.py           # Builds prompt context from DB
      prompts.py                   # System prompts and templates

    reminders/                     # Reminder service
      __init__.py
      service.py                   # Reminder scheduler + notification dispatch
      sounds.py                    # Sound playback
      assets/                      # .wav sound files

    api/                           # FastAPI route modules
      __init__.py
      auth.py                      # OAuth routes
      schedule.py                  # Schedule CRUD
      tasks.py                     # Task CRUD
      events.py                    # Events listing
      sync.py                      # Sync triggers + status
      preferences.py               # User preferences

  ui/
    planner_window.py              # pywebview launcher

frontend/                          # React app (separate build)
  package.json
  vite.config.ts
  src/
    App.tsx
    components/
      Calendar.tsx                 # FullCalendar wrapper
      TaskList.tsx                 # Three-column task view
      Sidebar.tsx                  # Navigation + What's Next
      ScheduleBlock.tsx            # Individual block component
      Settings.tsx                 # Account management + preferences
      ReminderToast.tsx            # In-app reminder display
    hooks/
      useSchedule.ts               # Schedule data fetching
      useTasks.ts                  # Task data fetching
      useSync.ts                   # Sync status polling
    api/
      client.ts                    # FastAPI client
    types/
      index.ts                     # TypeScript interfaces
```

---

## 10. Phased Delivery

Given the scope, this feature should be built in phases:

**Phase 1 — Foundation:** FastAPI backend, SQLite database, pywebview launcher, basic React shell with calendar view, preferences store

**Phase 2 — Google Integration:** OAuth 2.0 flow, Gmail sync + email parsing, Google Calendar sync, events displayed on calendar

**Phase 3 — Canvas Integration:** Playwright scraper setup, assignment/grade extraction, tasks populated from Canvas

**Phase 4 — AI Scheduling Engine:** Claude API integration, morning plan generation, continuous replanning, structured output parsing

**Phase 5 — Full UI:** Today/Tasks/Week views, drag-drop rescheduling, task management, What's Next panel

**Phase 6 — Reminders & Polish:** Notification system, sound alerts, nudge system, quiet hours, token optimization
