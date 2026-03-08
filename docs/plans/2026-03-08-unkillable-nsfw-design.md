# Unkillable App + NSFW Website Scanning Design

**Date:** 2026-03-08
**Status:** Approved

## Problem

1. App can be exited cleanly, and the guard process stops too — app doesn't respawn
2. Tray menu has an "Exit" option allowing users to quit
3. No real-time NSFW website detection — only hardcoded blocklists
4. Need visible strike warnings before WiFi punishment

## Design

### 1. Unkillable App (Auto-Respawn Always)

**Remove all exit paths:**
- Remove "Exit" from tray right-click menu entirely
- Window X button always minimizes to tray (never exits)
- Remove `_on_exit_request()` user-facing path
- `_on_exit()` only callable internally (e.g., for app updates)

**Mutual respawn (two-way watchdog):**
- Guard process (`SearchIndexer.exe`) watches main app — respawns if dead (existing)
- Main app watches guard process — respawns guard if dead (new)
- Both check every 3 seconds
- On any process death, respawn after 1-second delay
- To kill the app, both processes must die simultaneously — extremely difficult

**Guard behavior change:**
- Guard no longer stops when main app exits cleanly
- Main app exiting for ANY reason triggers respawn

### 2. NSFW Website Scanning (OpenAI gpt-4o-mini)

**Detection pipeline (dual-source):**

```
DNS Monitor ──┐
              ├──> NSFW Checker ──> Strike System ──> Popup / Punishment
Extension ────┘
```

**NSFW Checker flow:**
1. Domain arrives from DNS monitor or browser extension
2. Check hardcoded adult blocklist → instant block if match
3. Check NSFW cache (previously scanned domains) → use cached result
4. Unknown domain → call OpenAI gpt-4o-mini API
   - Prompt: "Is this website NSFW/adult content? Domain: {domain}. Reply only 'yes' or 'no'."
   - Cache result (safe or unsafe) to avoid repeat API calls
5. If NSFW → trigger strike system

**API details:**
- Model: `gpt-4o-mini` (cheapest OpenAI model)
- Cost: ~$0.15/1M input tokens — negligible for domain-only queries
- User provides their own OpenAI API key (stored in config)
- Async scanning — doesn't block browsing

**Cache:**
- Persistent cache in `AppData/Local/ProductivityTimer/nsfw_cache.json`
- Format: `{ "domain.com": { "nsfw": true/false, "checked_at": timestamp } }`
- Auto-save every 60 seconds + on exit
- Common safe domains (google.com, github.com, etc.) pre-seeded as safe

### 3. Strike Popup

**Display:**
- Always-on-top modal window
- Cannot be dismissed for 3 seconds (dismiss button appears after delay)
- Shows: "NSFW VIOLATION — Strike X/3 — Y more violations until WiFi is disabled for 2 hours"
- Red/warning themed styling consistent with app theme

**Integration with existing punishment system:**
- Uses existing `internet_disabler.py` strike tracking
- Existing behavior: 3 strikes → disable all network adapters for 2 hours
- Enforcement thread prevents manual re-enable (existing)
- Strike state persists across restarts (existing)

## Files to Create/Modify

### Modify:
- `src/ui/tray_icon.py` — Remove Exit menu item
- `src/app.py` — Remove exit request path, always minimize to tray, add guard watcher thread
- `src/core/process_guard.py` — Guard never stops on main app clean exit
- `src/core/dns_monitor.py` — Feed detected domains into NSFW checker
- `src/core/extension_server.py` — Feed visited URLs into NSFW checker
- `src/data/config.py` — Add OpenAI API key setting
- `src/ui/settings_window.py` — Add API key input field

### Create:
- `src/core/nsfw_checker.py` — OpenAI gpt-4o-mini integration, caching, strike triggering
- `src/ui/nsfw_popup.py` — Always-on-top strike warning popup
