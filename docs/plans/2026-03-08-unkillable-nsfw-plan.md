# Unkillable App + NSFW Strike Popup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the app completely unkillable (no exit paths, mutual respawn) and show an always-on-top NSFW violation popup with strike counter on each violation.

**Architecture:** Remove all user-facing exit paths from tray and window. Add mutual watchdog between main app and guard process. Create a new NSFW strike popup that fires on every adult site detection (not just when punishment triggers). The NSFW detection pipeline already exists (moderation API + gpt-4o-mini + DNS monitor + extension) — we just need to wire in the popup.

**Tech Stack:** Python, Tkinter/ttkbootstrap, pystray, psutil, subprocess

---

### Task 1: Remove Exit from Tray Menu

**Files:**
- Modify: `src/ui/tray_icon.py`

**Step 1: Remove on_exit parameter and Exit menu item**

Edit `src/ui/tray_icon.py` — remove `on_exit` from `__init__` parameters and the Exit menu item from `_setup_icon`:

```python
class TrayIcon:
    def __init__(
        self,
        on_show: Callable,
        on_start: Callable,
        on_pause: Callable,
        on_stop: Callable,
        on_settings: Callable,
    ):
        self.on_show = on_show
        self.on_start = on_start
        self.on_pause = on_pause
        self.on_stop = on_stop
        self.on_settings = on_settings

        self._icon: Optional[Icon] = None
        self._current_state = TimerState.IDLE

        if PYSTRAY_AVAILABLE:
            self._setup_icon()
```

Remove the Exit menu item and its separator from `_setup_icon`:

```python
    def _setup_icon(self) -> None:
        image = self._create_icon_image()

        menu = Menu(
            MenuItem("Show Timer", self._on_show_click, default=True),
            Menu.SEPARATOR,
            MenuItem("Start Session", self._on_start_click),
            MenuItem("Pause", self._on_pause_click),
            MenuItem("Stop Session", self._on_stop_click),
            Menu.SEPARATOR,
            MenuItem("Settings", self._on_settings_click),
        )

        self._icon = Icon(
            "ProductivityTimer",
            image,
            "Productivity Timer",
            menu
        )
```

Remove the `_on_exit_click` method entirely.

**Step 2: Verify the change**

Run: `python -c "from src.ui.tray_icon import TrayIcon; print('OK')"`
Expected: OK (no import errors)

**Step 3: Commit**

```bash
git add src/ui/tray_icon.py
git commit -m "remove Exit option from tray menu"
```

---

### Task 2: Remove All Exit Paths from App

**Files:**
- Modify: `src/app.py`

**Step 1: Update `_init_tray` to not pass `on_exit`**

```python
    def _init_tray(self) -> None:
        self.tray_icon = TrayIcon(
            on_show=self._on_tray_show,
            on_start=self._on_start,
            on_pause=self._on_pause,
            on_stop=self._on_stop,
            on_settings=self._on_settings,
        )

        if self.tray_icon.is_available():
            self.tray_icon.start()
```

**Step 2: Make `_on_close` always minimize to tray**

Replace the entire `_on_close` method:

```python
    def _on_close(self) -> None:
        """Handle window close - always minimize to tray."""
        if self.tray_icon.is_available():
            self.main_window.hide()
        # If no tray available, just ignore the close request
```

**Step 3: Remove `_on_exit_request`, `_handle_exit_request`, and `_show_exit_challenge` methods**

Delete these three methods entirely (lines 723-769 in app.py):
- `_on_exit_request`
- `_handle_exit_request`
- `_show_exit_challenge`

**Step 4: Verify**

Run: `python -c "from src.app import ProductivityApp; print('OK')"`
Expected: OK

**Step 5: Commit**

```bash
git add src/app.py
git commit -m "remove all user-facing exit paths, always minimize to tray"
```

---

### Task 3: Add Mutual Respawn — Main App Watches Guard

**Files:**
- Modify: `src/app.py`
- Modify: `src/core/process_guard.py`

**Step 1: Add guard watcher to `process_guard.py`**

Add a function that the main app calls to respawn the guard if it dies:

```python
def find_guard_exe() -> Optional[Path]:
    """Find the guard process executable."""
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        for name in ["SearchIndexer.exe"]:
            candidate = exe_dir / name
            if candidate.exists() and candidate.name != Path(sys.executable).name:
                return candidate
    return None


def is_guard_running() -> bool:
    """Check if the guard process is currently running."""
    if not getattr(sys, 'frozen', False):
        return True  # Skip guard watching in dev mode
    guard_exe = find_guard_exe()
    if guard_exe is None:
        return True  # No guard exe found, skip
    return is_process_running(guard_exe.name)


def respawn_guard() -> bool:
    """Respawn the guard process if it's not running."""
    if not getattr(sys, 'frozen', False):
        return True  # Skip in dev mode
    guard_exe = find_guard_exe()
    if guard_exe is None:
        return False
    try:
        subprocess.Popen(
            [str(guard_exe)],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return True
    except Exception as e:
        print(f"Failed to respawn guard: {e}")
        return False
```

**Step 2: Add guard watcher thread to `app.py`**

Add a method and start it in `__init__` after tray init:

```python
    def _start_guard_watcher(self) -> None:
        """Start a background thread that ensures the guard process stays alive."""
        import src.core.process_guard as pg

        def watch_loop():
            while True:
                try:
                    if not pg.is_guard_running():
                        print("Guard process died! Respawning...")
                        pg.respawn_guard()
                except Exception as e:
                    print(f"Guard watcher error: {e}")
                time.sleep(3)

        thread = threading.Thread(target=watch_loop, daemon=True)
        thread.start()
```

Add `import threading` at top of app.py (already imported via other modules, but verify).

Call `self._start_guard_watcher()` at the end of `__init__`, after `_init_desktop_stats()`.

**Step 3: Verify**

Run: `python -c "from src.core.process_guard import find_guard_exe, is_guard_running, respawn_guard; print('OK')"`
Expected: OK

**Step 4: Commit**

```bash
git add src/app.py src/core/process_guard.py
git commit -m "add mutual respawn - main app watches and respawns guard process"
```

---

### Task 4: Create NSFW Strike Popup

**Files:**
- Create: `src/ui/nsfw_popup.py`

**Step 1: Create the popup module**

Create `src/ui/nsfw_popup.py`:

```python
"""
Always-on-top NSFW violation popup with strike counter.
Shows when user visits an NSFW site, displaying current strike count
and how many strikes remain before WiFi is disabled.
"""

import tkinter as tk
import threading


class NSFWStrikePopup:
    """
    Always-on-top popup that warns the user about NSFW violations.
    Cannot be dismissed for 3 seconds.
    """

    def __init__(
        self,
        parent: tk.Tk,
        strike_count: int,
        max_strikes: int,
        punishment_hours: int,
        domain: str = "",
    ):
        self.parent = parent
        self.strike_count = strike_count
        self.max_strikes = max_strikes
        self.punishment_hours = punishment_hours
        self.domain = domain

        self._build_popup()

    def _build_popup(self) -> None:
        """Build and display the popup window."""
        self.popup = tk.Toplevel(self.parent)
        self.popup.title("NSFW VIOLATION")
        self.popup.configure(bg="#1a1a2e")

        # Always on top, no close button
        self.popup.attributes("-topmost", True)
        self.popup.overrideredirect(False)
        self.popup.protocol("WM_DELETE_WINDOW", lambda: None)  # Block close

        # Size and center on screen
        width, height = 500, 320
        screen_w = self.popup.winfo_screenwidth()
        screen_h = self.popup.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.popup.geometry(f"{width}x{height}+{x}+{y}")

        # Main container
        container = tk.Frame(self.popup, bg="#1a1a2e", padx=30, pady=20)
        container.pack(fill=tk.BOTH, expand=True)

        # Warning icon / header
        header = tk.Label(
            container,
            text="NSFW VIOLATION",
            font=("Helvetica", 22, "bold"),
            fg="#ff4757",
            bg="#1a1a2e",
        )
        header.pack(pady=(10, 5))

        # Domain that triggered it
        if self.domain:
            domain_label = tk.Label(
                container,
                text=f"Detected: {self.domain}",
                font=("Helvetica", 10),
                fg="#a0a0a0",
                bg="#1a1a2e",
            )
            domain_label.pack(pady=(0, 10))

        # Strike counter
        strikes_remaining = max(0, self.max_strikes - self.strike_count)
        strike_text = f"Strike {self.strike_count} / {self.max_strikes}"

        strike_label = tk.Label(
            container,
            text=strike_text,
            font=("Helvetica", 28, "bold"),
            fg="#ffa502",
            bg="#1a1a2e",
        )
        strike_label.pack(pady=(10, 5))

        # Warning message
        if strikes_remaining > 0:
            warn_text = (
                f"{strikes_remaining} more violation{'s' if strikes_remaining != 1 else ''} "
                f"until WiFi is disabled for {self.punishment_hours} hours"
            )
            warn_color = "#ffa502"
        else:
            warn_text = (
                f"WiFi has been DISABLED for {self.punishment_hours} hours.\n"
                "This cannot be bypassed."
            )
            warn_color = "#ff4757"

        warn_label = tk.Label(
            container,
            text=warn_text,
            font=("Helvetica", 12),
            fg=warn_color,
            bg="#1a1a2e",
            wraplength=420,
        )
        warn_label.pack(pady=(5, 20))

        # Dismiss button (hidden for 3 seconds)
        self.dismiss_btn = tk.Button(
            container,
            text="Dismiss (3s)",
            font=("Helvetica", 11),
            fg="#ffffff",
            bg="#444444",
            activebackground="#555555",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            state=tk.DISABLED,
            command=self._dismiss,
            padx=20,
            pady=8,
        )
        self.dismiss_btn.pack(pady=(10, 0))

        # Start countdown to enable dismiss
        self._countdown(3)

        # Force focus
        self.popup.focus_force()
        self.popup.grab_set()

    def _countdown(self, seconds_left: int) -> None:
        """Countdown before dismiss button becomes active."""
        if seconds_left > 0:
            self.dismiss_btn.configure(text=f"Dismiss ({seconds_left}s)")
            self.popup.after(1000, lambda: self._countdown(seconds_left - 1))
        else:
            self.dismiss_btn.configure(
                text="Dismiss",
                state=tk.NORMAL,
                bg="#e74c3c",
            )

    def _dismiss(self) -> None:
        """Dismiss the popup."""
        try:
            self.popup.grab_release()
            self.popup.destroy()
        except tk.TclError:
            pass
```

**Step 2: Verify**

Run: `python -c "from src.ui.nsfw_popup import NSFWStrikePopup; print('OK')"`
Expected: OK

**Step 3: Commit**

```bash
git add src/ui/nsfw_popup.py
git commit -m "add always-on-top NSFW strike popup with countdown dismiss"
```

---

### Task 5: Wire NSFW Popup into Strike System

**Files:**
- Modify: `src/app.py`

**Step 1: Add import for NSFWStrikePopup**

Add to imports at top of `app.py`:

```python
from src.ui.nsfw_popup import NSFWStrikePopup
```

**Step 2: Update `_on_adult_strike` to show popup on every strike**

Replace the existing `_on_adult_strike` method:

```python
    def _on_adult_strike(self, domain: str = "") -> dict:
        """Handle adult site visit attempt - show popup and add strike."""
        new_count, triggered = self.internet_disabler.add_strike()

        # Show strike popup on every violation (not just when punishment triggers)
        self.root.after(0, lambda: NSFWStrikePopup(
            parent=self.root,
            strike_count=new_count,
            max_strikes=self.config.max_adult_strikes,
            punishment_hours=self.config.punishment_hours,
            domain=domain,
        ))

        if triggered:
            # Punishment was triggered - also show the internet disabled notification
            self.root.after(500, self._show_punishment_notification)

        return self._get_punishment_state()
```

**Step 3: Update callers to pass domain**

In `_on_nsfw_domain_detected`, pass the domain to the strike:

```python
    def _on_nsfw_domain_detected(self, domain: str) -> None:
        """Handle newly detected NSFW domain - add to blocklists and fire strike."""
        print(f"[NSFW] AI detected NSFW domain: {domain}")

        # Add to always_blocked in extension server
        ExtensionRequestHandler.always_blocked_sites.add(domain)

        # Add to hosts file blocker if admin
        if self.has_admin and hasattr(self, 'website_blocker'):
            self.website_blocker.add_adult_site(domain)

        # Fire adult strike with domain info
        self.root.after(0, lambda d=domain: self._on_adult_strike(d))
```

Update the extension server adult strike callback setup in `_init_punishment_system` to support domain passing. The extension server's `_handle_adult_strike` calls the callback without domain, so we keep the default parameter:

The `_on_adult_strike` already has `domain: str = ""` as default, so the extension server callback will work as-is.

**Step 4: Verify**

Run: `python -c "from src.app import ProductivityApp; print('OK')"`
Expected: OK

**Step 5: Commit**

```bash
git add src/app.py
git commit -m "wire NSFW strike popup into violation detection - shows on every strike"
```

---

### Task 6: Final Integration Test

**Step 1: Run the app**

```bash
python run.py
```

Verify:
- [ ] No "Exit" option in tray right-click menu
- [ ] Clicking X on window minimizes to tray (does not exit)
- [ ] App cannot be closed by any user action
- [ ] Guard watcher thread starts (check console output)

**Step 2: Test NSFW popup (if API key configured)**

- Visit a known NSFW domain
- Verify popup appears with strike count
- Verify popup cannot be dismissed for 3 seconds
- Verify popup is always on top

**Step 3: Commit any fixes**

```bash
git add -A
git commit -m "final integration fixes for unkillable app + NSFW popup"
```
