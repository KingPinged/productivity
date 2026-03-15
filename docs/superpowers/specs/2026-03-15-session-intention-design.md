# Session Intention Feature — Design Spec

## Purpose

Keep users focused on their stated goal during a productivity session. When a session starts, the user declares what they intend to accomplish. That intention is displayed on the timer window and in a persistent top-of-screen bar throughout the session.

## Components

### 1. Intention Input Popup

**When:** Appears when the user clicks **Start** (before `timer.start_work()` is called). Only shows when `_session_active` is False (new session, not resuming from pause). This includes clicking Start after all sets complete and `_session_active` has been reset — the user gets a fresh intention prompt for the new session.

**Behavior:**
- Modal dialog centered on the main window
- Text input field with placeholder: "e.g. Finish the login page redesign"
- Max 100 characters — input is capped, remaining count shown
- Title: "What's your intention?" with subtitle "Stay focused. No side quests."
- Two buttons: "Start Session" (primary) and "Skip" (secondary)
- Enter key submits the text, Escape skips
- Skip starts the session with no intention (empty string)
- Empty text input + Start Session also counts as skip
- After submit/skip, the session begins normally (`timer.start_work()`)

**UI Details:**
- Dark theme matching existing app style (bg `#222244`, input bg `#1a1a2e`)
- Uses `ttk.Toplevel` with `transient(parent)` and `grab_set()` — same pattern as TypingChallengeDialog
- Size: ~450px wide, auto height
- Centered on parent window

### 2. Top-of-Screen Intention Bar

**When:** Shown immediately after intention is submitted with non-empty text. Visible during WORKING, BREAK, and PAUSED states. Also visible during the long break after all sets complete (bar is tied to its own existence, not `_session_active`).

**Destruction:** Bar is destroyed in `_do_stop()` — the same place where `_session_active` is reset and blocking stops. This covers both user-initiated stop (after typing challenge) and natural session end. If the user cancels the typing challenge, the bar survives because `_do_stop()` was never called.

**Behavior:**
- Frameless always-on-top window (`overrideredirect(True)`, `attributes("-topmost", True)`)
- Horizontally centered at the top of the primary monitor (uses `winfo_screenwidth()`, consistent with existing toast/popup positioning)
- Displays: "🎯 {intention text}" — truncated with ellipsis if over 80 chars displayed width
- On mouse enter: window opacity goes to 0.02 (near-invisible but avoids platform edge cases with 0.0)
- On mouse leave: window opacity returns to 0.92
- Does NOT pass through clicks — just becomes invisible while hovered

**UI Details:**
- Semi-transparent dark background via tkinter alpha (0.92)
- Rectangular shape (no rounded corners — `overrideredirect` windows don't support native rounding on Windows without fragile workarounds)
- Font: 13px, light purple/blue text color (`#d0d0ff`)
- Padding: 6px vertical, 28px horizontal
- No window frame, no title bar, no close button

**Lifecycle:**
- Created when session starts with non-empty intention
- Destroyed in `_do_stop()` (session end, user stop)
- Re-shown if it was hidden (e.g., app restores from tray)

### 3. Timer Window Integration

**Where:** New label in `MainWindow`, positioned below the state label and above the cycle counter.

**Behavior:**
- Displays: "🎯 {intention text}" in italic
- Text truncated with ellipsis if over 35 chars (fits the 400px window)
- Color: `#8888cc` (muted purple, distinct from state colors)
- Hidden when no intention is set
- Cleared when session ends (`_do_stop()`)

**UI Details:**
- Font: 13px italic
- Uses existing label pattern (`ttk.Label` or `tk.Label`)
- `pack()` between state label and cycle counter

## State Management

- `_session_intention: str` — stored on `ProductivityApp` instance
- Set when intention popup is submitted, cleared in `_do_stop()`
- Not persisted to disk — intention is per-session only

## Files to Modify

| File | Change |
|------|--------|
| `src/ui/intention_popup.py` | **New file** — IntentionPopup dialog class |
| `src/ui/intention_bar.py` | **New file** — IntentionBar top-of-screen overlay |
| `src/ui/main_window.py` | Add intention label below state label |
| `src/app.py` | Show popup on Start, manage bar lifecycle, store intention state |

## Applies to Both Platforms

All changes apply to both `src/` (Windows) and `productivity-mac/src/` (Mac). The implementation is identical — tkinter works the same on both platforms, with the exception that `overrideredirect` on macOS may need testing for the intention bar.
