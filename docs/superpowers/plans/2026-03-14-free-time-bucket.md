# Free Time Bucket Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reward system where completing pomodoros earns free time that lets users use blocklisted apps/websites during IDLE state. When the bucket is empty, blocking activates outside of work sessions.

**Architecture:** New `FreeTimeBucket` class owns all bucket state (balance, earning, draining) with JSON persistence. It integrates with existing `_on_usage_tick` and `_on_website_usage` callbacks to drain, with `_on_session_complete` and `_do_stop` to accumulate, and with `_start_blocking`/`_stop_blocking` to enforce. Config gets two new fields; UI gets a balance display and settings section.

**Tech Stack:** Python 3, ttkbootstrap (UI), threading (concurrency), JSON (persistence)

**Spec:** `docs/superpowers/specs/2026-03-14-free-time-bucket-design.md`

---

## Chunk 1: Core Data Layer

### Task 1: Add constants

**Files:**
- Modify: `src/utils/constants.py:36-41`

- [ ] **Step 1: Add free time bucket constants**

Add after line 37 (`NSFW_CACHE_FILE`):

```python
FREE_TIME_BUCKET_FILE = APP_DATA_DIR / "free_time_bucket.json"
FREE_TIME_WARNING_SECONDS = 120  # 2-minute warning before bucket empties
DEFAULT_FREE_TIME_RATIO = 2.0  # minutes of free time per minute of work
```

- [ ] **Step 2: Commit**

```bash
git add src/utils/constants.py
git commit -m "feat: add free time bucket constants"
```

---

### Task 2: Add config fields

**Files:**
- Modify: `src/data/config.py:66-67` (after `openai_api_key`), and `_on_save` in settings

- [ ] **Step 1: Add config fields**

In `src/data/config.py`, add the import at the top (with existing imports from constants):

```python
from src.utils.constants import DEFAULT_FREE_TIME_RATIO
```

Then add after line 67 (`openai_api_key: str = ""`):

```python
    # Free time bucket settings
    free_time_bucket_enabled: bool = False
    free_time_ratio: float = DEFAULT_FREE_TIME_RATIO  # free minutes per work minute
```

- [ ] **Step 2: Commit**

```bash
git add src/data/config.py
git commit -m "feat: add free_time_bucket_enabled and free_time_ratio config fields"
```

---

### Task 3: Create FreeTimeBucket class

**Files:**
- Create: `src/core/free_time_bucket.py`

- [ ] **Step 1: Create the FreeTimeBucket class**

```python
"""
Persistent free time bucket that tracks earned leisure time.
Users earn free time by completing pomodoro work sessions.
Time drains only when actively using blocklisted apps/websites during IDLE.
"""

import json
import threading
from typing import Callable, Optional

from src.utils.constants import FREE_TIME_BUCKET_FILE, APP_DATA_DIR, FREE_TIME_WARNING_SECONDS


class FreeTimeBucket:
    """
    Thread-safe persistent bucket for free time balance.
    Follows the same pattern as NSFWCache and UsageData.
    """

    def __init__(self, on_bucket_empty: Optional[Callable] = None,
                 on_warning: Optional[Callable] = None,
                 on_time_earned: Optional[Callable[[float], None]] = None):
        self._lock = threading.Lock()
        self.balance_seconds: float = 0.0
        self.total_earned_seconds: float = 0.0
        self.total_used_seconds: float = 0.0
        self.is_draining: bool = False
        self._dirty: bool = False
        self._warning_shown: bool = False  # one warning per drain-to-zero cycle

        # Callbacks
        self._on_bucket_empty = on_bucket_empty
        self._on_warning = on_warning
        self._on_time_earned = on_time_earned

    def has_time(self) -> bool:
        """Check if bucket has any free time remaining."""
        with self._lock:
            return self.balance_seconds > 0

    def get_balance(self) -> float:
        """Get current balance in seconds."""
        with self._lock:
            return self.balance_seconds

    def add_time(self, seconds: float) -> None:
        """Add earned free time to the bucket."""
        if seconds <= 0:
            return
        with self._lock:
            self.balance_seconds += seconds
            self.total_earned_seconds += seconds
            self._dirty = True
            # Reset warning flag when balance goes above threshold
            if self.balance_seconds > FREE_TIME_WARNING_SECONDS:
                self._warning_shown = False
        if self._on_time_earned:
            self._on_time_earned(seconds)

    def drain(self, seconds: float) -> None:
        """
        Drain free time from the bucket.
        Triggers warning callback at threshold and empty callback at zero.
        """
        if seconds <= 0:
            return

        trigger_warning = False
        trigger_empty = False

        with self._lock:
            if self.balance_seconds <= 0:
                return

            self.balance_seconds = max(0.0, self.balance_seconds - seconds)
            self.total_used_seconds += seconds
            self._dirty = True

            # Check warning threshold
            if (self.balance_seconds <= FREE_TIME_WARNING_SECONDS
                    and self.balance_seconds > 0
                    and not self._warning_shown):
                self._warning_shown = True
                trigger_warning = True

            # Check empty
            if self.balance_seconds <= 0:
                self.balance_seconds = 0.0
                self.is_draining = False
                trigger_empty = True

        # Fire callbacks outside the lock to avoid deadlocks
        if trigger_warning and self._on_warning:
            self._on_warning()
        if trigger_empty and self._on_bucket_empty:
            self._on_bucket_empty()

    def set_draining(self, draining: bool) -> None:
        """Set whether the bucket is actively draining."""
        with self._lock:
            self.is_draining = draining

    def is_dirty(self) -> bool:
        """Check if bucket has unsaved changes."""
        return self._dirty

    def save(self) -> None:
        """Save bucket state to disk."""
        with self._lock:
            if not self._dirty:
                return

            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

            data = {
                "balance_seconds": self.balance_seconds,
                "total_earned_seconds": self.total_earned_seconds,
                "total_used_seconds": self.total_used_seconds,
            }

            try:
                with open(FREE_TIME_BUCKET_FILE, 'w') as f:
                    json.dump(data, f, indent=2)
                self._dirty = False
            except Exception as e:
                print(f"Error saving free time bucket: {e}")

    @classmethod
    def load(cls, on_bucket_empty: Optional[Callable] = None,
             on_warning: Optional[Callable] = None,
             on_time_earned: Optional[Callable[[float], None]] = None) -> 'FreeTimeBucket':
        """Load bucket state from disk. Falls back to zero on corruption."""
        instance = cls(on_bucket_empty=on_bucket_empty,
                       on_warning=on_warning,
                       on_time_earned=on_time_earned)

        if not FREE_TIME_BUCKET_FILE.exists():
            return instance

        try:
            with open(FREE_TIME_BUCKET_FILE, 'r') as f:
                data = json.load(f)

            instance.balance_seconds = max(0.0, float(data.get("balance_seconds", 0.0)))
            instance.total_earned_seconds = max(0.0, float(data.get("total_earned_seconds", 0.0)))
            instance.total_used_seconds = max(0.0, float(data.get("total_used_seconds", 0.0)))

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            print(f"Error loading free time bucket (corrupted file, resetting): {e}")
        except Exception as e:
            print(f"Error loading free time bucket: {e}")

        return instance

    def format_balance(self, draining: bool = False) -> str:
        """Format balance for display. HH:MM:SS when draining, Xh Ym when static."""
        with self._lock:
            total_seconds = int(self.balance_seconds)

        if total_seconds <= 0:
            return "0m" if not draining else "00:00:00"

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        if draining:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            if hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"
```

- [ ] **Step 2: Verify the module imports correctly**

Run: `python -c "from src.core.free_time_bucket import FreeTimeBucket; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/core/free_time_bucket.py
git commit -m "feat: create FreeTimeBucket class with persistence and callbacks"
```

---

## Chunk 2: App Integration — Accumulation

### Task 4: Wire bucket into app initialization and accumulation

**Files:**
- Modify: `src/app.py:1-86` (imports + __init__), `src/app.py:468-495` (_on_session_complete), `src/app.py:651-663` (_do_stop), `src/app.py:758-782` (_on_exit)

- [ ] **Step 1: Add import**

At the top of `src/app.py`, add with the other imports:

```python
from src.core.free_time_bucket import FreeTimeBucket
```

- [ ] **Step 2: Initialize bucket in __init__**

In `src/app.py`, inside `__init__`, after all existing component initialization (after the line calling `_init_desktop_stats` or the last `_init_*` call), add:

```python
        # Initialize free time bucket
        self.free_time_bucket = FreeTimeBucket.load(
            on_bucket_empty=lambda: self.root.after(0, self._on_bucket_empty),
            on_warning=lambda: self.root.after(0, self._on_bucket_warning),
            on_time_earned=lambda secs: self.root.after(0, lambda s=secs: self._on_time_earned(s)),
        )
        self._schedule_bucket_save()
```

- [ ] **Step 3: Add bucket save scheduling**

Add near the other `_schedule_*` methods (after `_schedule_usage_save` around line 228):

```python
    def _schedule_bucket_save(self) -> None:
        """Schedule periodic free time bucket saves."""
        if self.free_time_bucket.is_dirty():
            self.free_time_bucket.save()
        self.root.after(60000, self._schedule_bucket_save)
```

- [ ] **Step 4: Add accumulation in _on_session_complete**

In `_on_session_complete`, inside the `if completed_state == TimerState.WORKING:` block (after `self.config.increment_cycle()` at line 472), add:

```python
            # Earn free time if bucket feature is enabled
            if self.config.free_time_bucket_enabled:
                earned = self.config.work_minutes * 60 * self.config.free_time_ratio
                self.free_time_bucket.add_time(earned)
```

- [ ] **Step 5: Add early-stop accumulation in _do_stop**

In `_do_stop` (line 651), add the elapsed time capture BEFORE `self.timer.stop()`:

```python
    def _do_stop(self) -> None:
        """Actually stop the timer and blocking."""
        # Capture elapsed work time before stop() resets _time_remaining
        if self.timer.state == TimerState.WORKING and self.config.free_time_bucket_enabled:
            elapsed = self.timer.work_seconds - self.timer.time_remaining
            if elapsed > 0:
                earned = elapsed * self.config.free_time_ratio
                self.free_time_bucket.add_time(earned)

        self.timer.stop()
        self._stop_blocking()
        self.disable_guard.end_session()

        # Reset sets tracking
        self._session_active = False
        self._sets_completed = 0
        self._update_sets_display()

        self.main_window.update_state(TimerState.IDLE)
        self.main_window.set_initial_time(self.config.work_minutes * 60)
```

- [ ] **Step 6: Add bucket save on exit**

In `_on_exit` (line 758), after `self.nsfw_cache.save()` block (around line 775), add:

```python
        # Save free time bucket
        self.free_time_bucket.save()
```

- [ ] **Step 7: Add callback methods**

Add these methods to the `ProductivityApp` class. Note: `_show_notification` only brings the window to front and beeps — it does NOT display text. Use the `Toast` class directly for visible messages. Add the import at the top of `app.py`:

```python
from src.ui.toast import Toast
```

Then add these methods:

```python
    def _on_bucket_empty(self) -> None:
        """Handle bucket draining to zero — activate blocking during IDLE."""
        if self.timer.state == TimerState.IDLE:
            self._start_blocking()
            Toast(self.root, "Free time used up - blocked apps/sites are now blocked",
                  accent="#e94560")

    def _on_bucket_warning(self) -> None:
        """Handle bucket approaching zero — show warning toast."""
        if self.timer.state == TimerState.IDLE:
            Toast(self.root, "2 minutes of free time remaining",
                  accent="#f0ad4e")

    def _on_time_earned(self, seconds: float) -> None:
        """Handle time earned — show notification and update display."""
        minutes = int(seconds / 60)
        Toast(self.root, f"Earned {minutes} minutes of free time!",
              accent="#0f9b58")
        self._update_bucket_display()
```

- [ ] **Step 8: Add startup blocking check**

After the bucket initialization and `_schedule_bucket_save()` in `__init__`, add:

```python
        # If bucket feature is enabled and bucket is empty at startup, activate blocking
        if (self.config.free_time_bucket_enabled
                and not self.free_time_bucket.has_time()):
            self.root.after(500, self._start_blocking)
```

- [ ] **Step 9: Commit**

```bash
git add src/app.py
git commit -m "feat: wire free time bucket into accumulation and lifecycle"
```

---

## Chunk 3: App Integration — Draining and Blocking

### Task 5: Add draining logic to usage callbacks

**Files:**
- Modify: `src/app.py:215-222` (_on_usage_tick, _on_website_usage)

- [ ] **Step 1: Add draining to _on_usage_tick**

Replace the existing `_on_usage_tick` method (line 215-217):

```python
    def _on_usage_tick(self, name: str, category: str, seconds: int) -> None:
        """Handle usage tick from app tracker."""
        self.usage_data.record_usage(name, category, seconds)

        # Drain free time bucket if using a blocked app during IDLE
        if (category == 'app'
                and self.config.free_time_bucket_enabled
                and self.timer.state == TimerState.IDLE
                and self.free_time_bucket.has_time()
                and name.lower() in (app.lower() for app in self.config.get_all_blocked_apps())):
            self.free_time_bucket.drain(seconds)
```

- [ ] **Step 2: Add draining to _on_website_usage**

Replace the existing `_on_website_usage` method (line 219-222):

```python
    def _on_website_usage(self, category: str, name: str, seconds: int) -> None:
        """Handle website usage report from extension."""
        print(f"Website usage: {name} - {seconds}s")
        self.usage_data.record_usage(name, category, seconds)

        # Drain free time bucket if using a blocked website during IDLE
        if (self.config.free_time_bucket_enabled
                and self.timer.state == TimerState.IDLE
                and self.free_time_bucket.has_time()
                and name.lower() in (site.lower() for site in self.config.get_all_blocked_websites())):
            self.free_time_bucket.drain(seconds)
```

- [ ] **Step 3: Commit**

```bash
git add src/app.py
git commit -m "feat: add free time bucket draining in usage callbacks"
```

---

### Task 6: Integrate bucket with blocking decisions

**Files:**
- Modify: `src/app.py:446-466` (_on_state_change), `src/app.py:534-581` (_start_blocking, _stop_blocking)

- [ ] **Step 1: Update _on_state_change for IDLE bucket blocking**

In `_on_state_change` (line 446), update the IDLE branch to check bucket state:

Replace lines 464-466:
```python
        elif new_state == TimerState.IDLE:
            self._stop_blocking()
            self.disable_guard.end_session()
```

With:
```python
        elif new_state == TimerState.IDLE:
            # If bucket feature is enabled and bucket is empty, keep blocking
            if (self.config.free_time_bucket_enabled
                    and not self.free_time_bucket.has_time()):
                # Stay blocked — don't call _stop_blocking
                pass
            else:
                self._stop_blocking()
            self.disable_guard.end_session()
```

- [ ] **Step 2: Add _on_bucket_empty blocking to handle mid-IDLE bucket drain**

The `_on_bucket_empty` method was already added in Task 4 Step 7. It calls `_start_blocking()` when in IDLE state. No additional changes needed.

- [ ] **Step 3: Update _on_time_earned to unblock if earned during IDLE**

Update the `_on_time_earned` method to also unblock if the user just earned time while in IDLE (this happens after a pomodoro cycle: WORKING -> BREAK -> IDLE, and the time is earned at the WORKING -> BREAK transition, so by the time we're IDLE the balance is already positive — but this handles edge cases):

The existing method is fine. The natural flow is: WORKING -> earn time -> BREAK -> IDLE. At the IDLE transition in `_on_state_change`, the bucket will have time (just earned), so `_stop_blocking()` is called. No extra logic needed.

- [ ] **Step 4: Commit**

```bash
git add src/app.py
git commit -m "feat: integrate free time bucket with blocking decisions on state change"
```

---

## Chunk 3: UI Integration

### Task 7: Add bucket display to main window

**Files:**
- Modify: `src/ui/main_window.py:90-116` (after state_label, before controls)

- [ ] **Step 1: Add free time label to main window**

In `src/ui/main_window.py`, after the state_label pack (line 90), add:

```python
        # Free time bucket display (hidden by default)
        self.free_time_label = ttk.Label(
            timer_frame,
            text="",
            font=("Helvetica", 12),
            bootstyle="info"
        )
        # Not packed initially — shown when feature is enabled
```

- [ ] **Step 2: Add update method for bucket display**

Add to the `MainWindow` class:

```python
    def update_free_time(self, text: str, visible: bool = True) -> None:
        """Update the free time bucket display."""
        if visible:
            self.free_time_label.config(text=f"Free Time: {text}")
            if not self.free_time_label.winfo_ismapped():
                self.free_time_label.pack(pady=(5, 0))
        else:
            if self.free_time_label.winfo_ismapped():
                self.free_time_label.pack_forget()
```

- [ ] **Step 3: Commit**

```bash
git add src/ui/main_window.py
git commit -m "feat: add free time balance display to main window"
```

---

### Task 8: Wire bucket display updates in app

**Files:**
- Modify: `src/app.py` (tick handler, state change handler)

- [ ] **Step 1: Add _update_bucket_display method**

Add to the `ProductivityApp` class:

```python
    def _update_bucket_display(self) -> None:
        """Update the free time bucket display in the main window."""
        if not self.config.free_time_bucket_enabled:
            self.main_window.update_free_time("", visible=False)
            return

        is_draining = (self.timer.state == TimerState.IDLE
                       and self.free_time_bucket.has_time())
        text = self.free_time_bucket.format_balance(draining=is_draining)
        self.main_window.update_free_time(text, visible=True)
```

- [ ] **Step 2: Call _update_bucket_display from timer tick**

In `_on_timer_tick` (around line 424), add at the end of the method:

```python
        # Update bucket display
        if self.config.free_time_bucket_enabled:
            self.root.after(0, self._update_bucket_display)
```

- [ ] **Step 3: Call _update_bucket_display from state change**

In `_on_state_change` (line 446), add at the end of the method:

```python
        # Update bucket display on state change
        self.root.after(0, self._update_bucket_display)
```

- [ ] **Step 4: Call _update_bucket_display on app init**

In `__init__`, after the bucket initialization (added in Task 4), add:

```python
        # Set initial bucket display
        self.root.after(100, self._update_bucket_display)
```

- [ ] **Step 5: Update tray tooltip to include bucket balance**

In `_on_timer_tick`, update the tray tooltip line (around line 440-444). Replace the existing tooltip update:

```python
        # Build tooltip with optional free time info
        tooltip = f"{state_upper} - {minutes:02d}:{secs:02d} | Cycles: {cycles_today}"
        if self.config.free_time_bucket_enabled:
            bucket_text = self.free_time_bucket.format_balance(draining=False)
            tooltip += f" | Free: {bucket_text}"

        self.root.after(
            0,
            lambda t=tooltip: self.tray_icon.update_tooltip(t)
        )
```

- [ ] **Step 6: Add bucket re-evaluation to _on_settings_save**

In `_on_settings_save` (line 685), add at the end of the method:

```python
        # Re-evaluate bucket display and blocking state after settings change
        self._update_bucket_display()
```

- [ ] **Step 7: Commit**

```bash
git add src/app.py
git commit -m "feat: wire free time bucket display updates to timer tick and state changes"
```

---

### Task 9: Add settings section for free time bucket

**Files:**
- Modify: `src/ui/settings_window.py:265-266` (after AI Content Detection, before buttons)

- [ ] **Step 1: Add Free Time Bucket settings section**

In `src/ui/settings_window.py`, after the `ai_help.pack()` line (line 265) and before the `# Buttons` comment (line 267), add:

```python
        # Free Time Bucket Section
        bucket_label = ttk.Label(
            main_frame,
            text="Free Time Bucket",
            font=("Helvetica", 14, "bold")
        )
        bucket_label.pack(anchor=W, pady=(10, 10))

        bucket_frame = ttk.Labelframe(main_frame, text="Reward System", padding=10)
        bucket_frame.pack(fill=X, pady=(0, 20))

        # Enable toggle
        self.bucket_enabled_var = ttk.BooleanVar(value=self.config.free_time_bucket_enabled)
        bucket_toggle = ttk.Checkbutton(
            bucket_frame,
            text="Enable Free Time Bucket",
            variable=self.bucket_enabled_var,
            bootstyle="round-toggle"
        )
        bucket_toggle.pack(anchor=W, pady=5)

        # Ratio setting
        ratio_frame = ttk.Frame(bucket_frame)
        ratio_frame.pack(fill=X, pady=5)

        ttk.Label(ratio_frame, text="Free minutes per work minute:").pack(side=LEFT)
        self.ratio_var = ttk.DoubleVar(value=self.config.free_time_ratio)
        ratio_spin = ttk.Spinbox(
            ratio_frame,
            from_=0.5,
            to=5.0,
            increment=0.5,
            textvariable=self.ratio_var,
            width=5
        )
        ratio_spin.pack(side=RIGHT)

        # Help text
        bucket_help = ttk.Label(
            bucket_frame,
            text="Earn free time by completing pomodoros. Free time drains\nonly when using blocked apps/sites outside work sessions.",
            font=("Helvetica", 8),
            bootstyle="secondary",
            wraplength=380
        )
        bucket_help.pack(anchor=W, pady=(5, 0))
```

- [ ] **Step 2: Add bucket fields to _on_save**

In `_on_save` (line 343), add after the `self.config.openai_api_key = self.api_key_var.get()` line (line 357):

```python
        self.config.free_time_bucket_enabled = self.bucket_enabled_var.get()
        self.config.free_time_ratio = self.ratio_var.get()
```

- [ ] **Step 3: Add bucket fields to unsaved changes detection**

In `_original_values` dict (line 39-50), add after `'openai_api_key'`:

```python
            'free_time_bucket_enabled': config.free_time_bucket_enabled,
            'free_time_ratio': config.free_time_ratio,
```

In `_get_current_values` method (line 304-320), add after `'openai_api_key'`:

```python
            'free_time_bucket_enabled': self.bucket_enabled_var.get(),
            'free_time_ratio': self.ratio_var.get(),
```

- [ ] **Step 4: Increase window height to accommodate new section**

In the geometry line (line 294), update the height:

```python
        height = 960  # Increased for free time bucket section
```

- [ ] **Step 5: Commit**

```bash
git add src/ui/settings_window.py
git commit -m "feat: add free time bucket settings section with toggle and ratio"
```

---

## Chunk 4: Final Integration and Testing

### Task 10: Manual integration test

- [ ] **Step 1: Verify app starts without errors**

Run: `python run.py`
Expected: App launches, no import errors

- [ ] **Step 2: Verify settings section appears**

Open Settings, scroll to "Free Time Bucket" section. Toggle should be OFF by default.

- [ ] **Step 3: Test accumulation**

1. Enable free time bucket in settings (ratio 2.0)
2. Start a pomodoro, then immediately stop it
3. Verify "Earned X minutes of free time!" notification appears
4. Verify free time balance shows in main window

- [ ] **Step 4: Test persistence**

1. Note the free time balance
2. Close and reopen the app
3. Verify balance is preserved

- [ ] **Step 5: Test blocking when bucket empty**

1. Enable free time bucket with 0 balance (or drain all time)
2. In IDLE state, verify that blocklisted apps/websites are blocked

- [ ] **Step 6: Test feature toggle off**

1. Disable free time bucket in settings
2. Verify IDLE state does not block anything (original behavior)
3. Verify balance is preserved (re-enable to check)

- [ ] **Step 7: Commit any fixes**

```bash
git add -A
git commit -m "fix: integration test fixes for free time bucket"
```
