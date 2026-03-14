# Free Time Bucket — Design Spec

## Overview

The Free Time Bucket is a reward system that lets users earn free time by completing pomodoro work sessions. Earned time is stored in a persistent bucket that drains only when the user actively uses blocklisted apps or websites during IDLE state. When the bucket is empty, blocklist blocking activates even outside of pomodoros.

The feature is toggled on/off in settings. When off, existing behavior is preserved (IDLE = unblocked).

## Requirements

- Users earn free time proportional to work completed (default: 2 minutes per 1 minute of work)
- Free time drains only when actively using blocklisted apps/websites during IDLE
- AFK time does not drain the bucket
- Break time is never affected — blocklist items are always unblocked during BREAK
- Adult sites remain always blocked regardless of bucket state
- When bucket hits 0, blocking activates immediately
- 2-minute warning toast before bucket empties
- Balance persists across app restarts indefinitely (intentional — users who earn time in bulk can save it)
- Feature can be toggled on/off; toggling off preserves existing balance
- PAUSED state: bucket does not drain regardless of what state was paused from
- Corrupted persistence file: fall back to zero balance (same pattern as Config.load())

## Data Model

### FreeTimeBucket class (`src/core/free_time_bucket.py`)

```
FreeTimeBucket:
  balance_seconds: float        # current free time remaining
  total_earned_seconds: float   # lifetime earned (stats)
  total_used_seconds: float     # lifetime used (stats)
  is_draining: bool             # currently draining
  _dirty: bool                  # needs save
  _lock: threading.Lock         # thread safety
```

Follows the same pattern as `NSFWCache` and `UsageData` — thread-safe with lock, dirty flag for debounced persistence, JSON file on disk.

### Persistence

File: `AppData\Local\ProductivityTimer\free_time_bucket.json`

```json
{
  "balance_seconds": 6240.0,
  "total_earned_seconds": 12480.0,
  "total_used_seconds": 6240.0
}
```

Saved every 60 seconds when dirty + on app exit.

### Config additions (`config.py`)

- `free_time_bucket_enabled: bool` — default `False`
- `free_time_ratio: float` — default `2.0` (minutes of free time per minute of work)

### Constants additions (`constants.py`)

- `FREE_TIME_BUCKET_FILE` — path to persistence file
- `FREE_TIME_WARNING_SECONDS = 120` — warning threshold
- `DEFAULT_FREE_TIME_RATIO = 2.0`

## Accumulation Logic

When a work session completes (WORKING -> BREAK transition):

```
earned = work_duration_seconds * config.free_time_ratio
bucket.add_time(earned)
```

- Hooks into existing `on_session_complete` callback in `app.py`, alongside `config.increment_cycle()`
- AFK-paused time does not count (timer already tracks only active work time)
- Early stop (manual stop during WORKING) earns proportional credit for time worked. Implementation note: elapsed time must be captured *before* `timer.stop()` is called, since `stop()` resets `_time_remaining`. Use `elapsed = timer.work_seconds - timer.time_remaining` before calling stop.
- Feature toggled off: no accumulation, but existing balance preserved

## Draining Logic

During IDLE state, the bucket drains only when using blocklisted apps/websites:

### App detection

The existing `UsageTracker` polls the active process every 1 second. Extended check:
- If active process is in blocklist AND timer is IDLE AND feature enabled AND bucket has balance:
  - `bucket.drain(1)` — subtract 1 second

### Website detection

The browser extension reports active website usage via extension server callback. Same logic:
- If domain is in blocklist during IDLE:
  - `bucket.drain(seconds)` for reported duration

### Warning system

- Balance drops below 120 seconds: show toast "2 minutes of free time remaining"
- Balance hits 0: activate blocking (kill blocked apps, update hosts file, sync extension)
- One warning toast per drain-to-zero cycle (resets when balance goes above threshold)

### Website draining detail

The existing `_on_website_usage` callback in `app.py` receives `(domain, seconds)` from the extension's POST to `/usage/website`. This callback fires for all websites. To integrate draining:
- Inside the existing callback, add a check: if timer is IDLE AND feature enabled AND domain is in `config.get_all_blocked_websites()`, call `bucket.drain(seconds)`.
- This reuses the existing extension reporting mechanism — no new endpoints needed.

### Not draining when

- Timer is in WORKING, BREAK, or PAUSED state
- User is using non-blocklisted apps/websites
- User is AFK
- Feature is toggled off

## Blocking Decision Integration

New decision tree for blocklist items (adult sites unchanged — always blocked):

```
Is timer WORKING?
  YES -> Block (unchanged)
Is timer PAUSED?
  YES -> Keep current blocking state (unchanged — if paused from WORKING, stay blocked)
Is timer BREAK?
  YES -> Don't block (unchanged)
Is timer IDLE?
  -> Is free time bucket enabled?
    NO  -> Don't block (unchanged)
    YES -> Does bucket have balance > 0?
      YES -> Don't block, drain bucket
      NO  -> Block
```

### Integration points

- **ProcessBlocker**: Extend to also run during IDLE when bucket is enabled and empty. Before killing during IDLE, check `bucket.has_time()`.
- **WebsiteBlocker**: Apply/remove hosts file blocks based on bucket state during IDLE.
- **ExtensionServer**: Sync blocking state to browser extension when bucket state changes.
- **ExtensionServer protocol**: No new endpoints needed. The existing `is_blocking` boolean is set to `true` when bucket empties during IDLE (same as during WORKING). The extension does not need to distinguish between work-blocking and bucket-empty-blocking — the effect is the same.
- **`app.py` `_start_blocking()` / `_stop_blocking()`**: New trigger path — bucket exhausted during IDLE triggers `_start_blocking()`. Starting a pomodoro also triggers `_start_blocking()` (existing). Transitioning to BREAK or IDLE-with-balance triggers `_stop_blocking()`.
- **Bucket-empty blocking responsiveness**: When `bucket.drain()` causes balance to hit 0, it should immediately call a callback (e.g. `on_bucket_empty`) that triggers `_start_blocking()`. Do not wait for the next ProcessBlocker cycle.
- **Break time**: Never affected. During BREAK, blocklist items always unblocked regardless of bucket balance.

## UI

### Main window

Display free time balance next to the timer:
- While draining: `HH:MM:SS` format (live countdown)
- While static: `Xh Ym` format
- Only visible when feature is enabled
- During WORKING/BREAK: show balance but do not drain (informational — user sees what they have banked)

### Settings window

New section "Free Time Bucket":
- Toggle: Enable/disable the feature
- Spinbox: Work-to-free-time ratio (default 2.0, range 0.5-5.0, step 0.5), labeled "Minutes of free time earned per minute of work"

### System tray

Add bucket balance to existing tooltip (e.g. "Cycles today: 3 | Free time: 1h 24m").

### Toast notifications

- After pomodoro: "Earned X minutes of free time!"
- 2-minute warning: "2 minutes of free time remaining"
- Bucket empty: "Free time used up - blocked apps/sites are now blocked"

## Files to create

- `src/core/free_time_bucket.py` — FreeTimeBucket class

## Files to modify

- `src/utils/constants.py` — add bucket constants
- `src/data/config.py` — add `free_time_bucket_enabled`, `free_time_ratio`
- `src/app.py` — wire bucket into accumulation, draining, and blocking decisions
- `src/core/process_guard.py` — extend blocking logic for IDLE+bucket-empty
- `src/ui/settings_window.py` — add Free Time Bucket settings section
- `src/ui/main_window.py` — display bucket balance (if this file exists, otherwise in app.py UI code)
- `browser_extension/background.js` — may need updates if extension needs to report blocked-site usage differently during IDLE (likely no changes needed since existing usage reporting + `is_blocking` boolean cover the requirements)
