# Session Intention Feature Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show an intention input popup when sessions start, display the intention on the timer window and in a persistent top-of-screen bar throughout the session.

**Architecture:** Three new UI components (IntentionPopup, IntentionBar, intention label in MainWindow) orchestrated by ProductivityApp. The popup intercepts `_on_start()` before `timer.start_work()`. The bar is a frameless topmost window. State is stored as `_session_intention` on the app instance — not persisted to disk.

**Tech Stack:** Python, tkinter, ttkbootstrap

---

## File Structure

| File | Role |
|------|------|
| `src/ui/intention_popup.py` | **New** — Modal dialog for intention input |
| `src/ui/intention_bar.py` | **New** — Frameless always-on-top bar at top of screen |
| `src/ui/main_window.py` | **Modify** — Add intention label below state label |
| `src/app.py` | **Modify** — Intercept Start, manage bar lifecycle, store intention |
| `productivity-mac/src/ui/intention_popup.py` | **New** — Copy of Windows version |
| `productivity-mac/src/ui/intention_bar.py` | **New** — Copy of Windows version |
| `productivity-mac/src/ui/main_window.py` | **Modify** — Same changes as Windows |
| `productivity-mac/src/app.py` | **Modify** — Same changes as Windows (plus `_save_session_state()` calls) |

---

## Chunk 1: Core UI Components (Windows)

### Task 1: Create IntentionPopup

**Files:**
- Create: `src/ui/intention_popup.py`

- [ ] **Step 1: Create the IntentionPopup class**

```python
"""Modal dialog for session intention input."""

import tkinter as tk


class IntentionPopup:
    """
    Modal popup that asks the user what they intend to accomplish.
    Shown when a new session starts (user clicks Start while IDLE).
    """

    MAX_CHARS = 100

    def __init__(self, parent: tk.Tk, on_submit: callable):
        """
        Args:
            parent: Parent window to center on
            on_submit: Callback with signature on_submit(intention: str).
                       Called with the text or "" if skipped.
        """
        self.parent = parent
        self.on_submit = on_submit
        self._result = ""

        self._build()

    def _build(self) -> None:
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Session Intention")
        self.dialog.configure(bg="#222244")
        self.dialog.transient(self.parent)
        self.dialog.resizable(False, False)

        # Block interaction with parent
        self.dialog.grab_set()
        self.dialog.protocol("WM_DELETE_WINDOW", self._skip)

        # Size and center on parent
        width, height = 450, 220
        px = self.parent.winfo_x() + (self.parent.winfo_width() - width) // 2
        py = self.parent.winfo_y() + (self.parent.winfo_height() - height) // 2
        self.dialog.geometry(f"{width}x{height}+{px}+{py}")

        container = tk.Frame(self.dialog, bg="#222244", padx=30, pady=20)
        container.pack(fill=tk.BOTH, expand=True)

        # Title
        tk.Label(
            container,
            text="What's your intention?",
            font=("Helvetica", 18, "bold"),
            fg="#e0e0e0",
            bg="#222244",
        ).pack(pady=(5, 2))

        # Subtitle
        tk.Label(
            container,
            text="Stay focused. No side quests.",
            font=("Helvetica", 11),
            fg="#888888",
            bg="#222244",
        ).pack(pady=(0, 12))

        # Text input
        self.entry_var = tk.StringVar()
        self.entry_var.trace_add("write", self._on_text_change)

        self.entry = tk.Entry(
            container,
            textvariable=self.entry_var,
            font=("Helvetica", 13),
            bg="#1a1a2e",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief=tk.FLAT,
            borderwidth=8,
        )
        self.entry.pack(fill=tk.X, pady=(0, 4))
        self.entry.focus_set()

        # Character counter
        self.char_label = tk.Label(
            container,
            text=f"0 / {self.MAX_CHARS}",
            font=("Helvetica", 9),
            fg="#666666",
            bg="#222244",
            anchor="e",
        )
        self.char_label.pack(fill=tk.X, pady=(0, 10))

        # Buttons
        btn_frame = tk.Frame(container, bg="#222244")
        btn_frame.pack()

        tk.Button(
            btn_frame,
            text="Start Session",
            font=("Helvetica", 11, "bold"),
            fg="#ffffff",
            bg="#4a90d9",
            activebackground="#5aa0e9",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=20,
            pady=6,
            command=self._submit,
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            btn_frame,
            text="Skip",
            font=("Helvetica", 11),
            fg="#888888",
            bg="#222244",
            activebackground="#2a2a4e",
            activeforeground="#aaaaaa",
            relief=tk.GROOVE,
            padx=16,
            pady=6,
            command=self._skip,
        ).pack(side=tk.LEFT)

        # Key bindings
        self.dialog.bind("<Return>", lambda e: self._submit())
        self.dialog.bind("<Escape>", lambda e: self._skip())

    def _on_text_change(self, *_args) -> None:
        """Enforce max chars and update counter."""
        text = self.entry_var.get()
        if len(text) > self.MAX_CHARS:
            self.entry_var.set(text[: self.MAX_CHARS])
            text = text[: self.MAX_CHARS]
        count = len(text)
        self.char_label.configure(text=f"{count} / {self.MAX_CHARS}")

    def _submit(self) -> None:
        text = self.entry_var.get().strip()
        self._close()
        self.on_submit(text)

    def _skip(self) -> None:
        self._close()
        self.on_submit("")

    def _close(self) -> None:
        try:
            self.dialog.grab_release()
            self.dialog.destroy()
        except tk.TclError:
            pass
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/intention_popup.py
git commit -m "feat: add IntentionPopup dialog class"
```

---

### Task 2: Create IntentionBar

**Files:**
- Create: `src/ui/intention_bar.py`

- [ ] **Step 1: Create the IntentionBar class**

```python
"""Frameless always-on-top bar showing session intention at top of screen."""

import tkinter as tk


class IntentionBar:
    """
    Slim overlay bar pinned to the top-center of the primary monitor.
    Becomes near-invisible on hover, reappears on mouse leave.
    """

    DISPLAY_MAX_CHARS = 80

    def __init__(self, root: tk.Tk, intention: str):
        """
        Args:
            root: The main tkinter root window
            intention: The intention text to display
        """
        self.root = root
        self._destroyed = False

        # Truncate for display
        display_text = intention
        if len(display_text) > self.DISPLAY_MAX_CHARS:
            display_text = display_text[: self.DISPLAY_MAX_CHARS - 1] + "…"

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.92)
        self.win.configure(bg="#1e1e3c")

        # Content
        self.label = tk.Label(
            self.win,
            text=f"\U0001f3af  {display_text}",
            font=("Helvetica", 13),
            fg="#d0d0ff",
            bg="#1e1e3c",
            padx=28,
            pady=6,
        )
        self.label.pack()

        # Position: top-center of primary monitor
        self.win.update_idletasks()
        bar_w = self.win.winfo_reqwidth()
        screen_w = self.win.winfo_screenwidth()
        x = (screen_w - bar_w) // 2
        self.win.geometry(f"+{x}+0")

        # Hover bindings
        self.win.bind("<Enter>", self._on_enter)
        self.win.bind("<Leave>", self._on_leave)
        self.label.bind("<Enter>", self._on_enter)
        self.label.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event) -> None:
        if not self._destroyed:
            self.win.attributes("-alpha", 0.02)

    def _on_leave(self, _event) -> None:
        if not self._destroyed:
            self.win.attributes("-alpha", 0.92)

    def destroy(self) -> None:
        """Remove the bar from screen."""
        if self._destroyed:
            return
        self._destroyed = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def show(self) -> None:
        """Re-show the bar (e.g. after app restores from tray)."""
        if not self._destroyed:
            try:
                self.win.deiconify()
                self.win.lift()
            except tk.TclError:
                pass

    def hide(self) -> None:
        """Temporarily hide the bar (e.g. when app minimizes to tray)."""
        if not self._destroyed:
            try:
                self.win.withdraw()
            except tk.TclError:
                pass
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/intention_bar.py
git commit -m "feat: add IntentionBar top-of-screen overlay"
```

---

### Task 3: Add intention label to MainWindow

**Files:**
- Modify: `src/ui/main_window.py` — after state_label, before cycle_frame

- [ ] **Step 1: Add intention label**

After the `self.state_label.pack(pady=(5, 0))` line (~line 91), add. Note: `main_window.py` uses `ttkbootstrap as ttk` but not raw `tkinter as tk`. Use `tk.Label` here for direct color control, so add `import tkinter as tk` at the top of the file if not already present.

```python
# Intention label (hidden by default)
self.intention_label = tk.Label(
    timer_frame,
    text="",
    font=("Helvetica", 13, "italic"),
    fg="#8888cc",
    bg=ttk.Style().lookup("TFrame", "background"),
)
# Not packed initially — shown when intention is set
```

- [ ] **Step 2: Add helper methods to MainWindow**

Add these methods to the `MainWindow` class:

```python
def set_intention(self, text: str) -> None:
    """Show or hide the intention label."""
    if text:
        display = text
        if len(display) > 35:
            display = display[:34] + "…"
        self.intention_label.configure(text=f"\U0001f3af {display}")
        self.intention_label.pack(pady=(4, 0))
    else:
        self.intention_label.pack_forget()

def clear_intention(self) -> None:
    """Clear and hide the intention label."""
    self.intention_label.configure(text="")
    self.intention_label.pack_forget()
```

- [ ] **Step 3: Commit**

```bash
git add src/ui/main_window.py
git commit -m "feat: add intention label to timer window"
```

---

### Task 4: Integrate into ProductivityApp (Windows)

**Files:**
- Modify: `src/app.py`

- [ ] **Step 1: Add imports**

At top of `src/app.py`, add:

```python
from src.ui.intention_popup import IntentionPopup
from src.ui.intention_bar import IntentionBar
```

- [ ] **Step 2: Add state fields in `__init__`**

After the `self._is_blocking = False` line (~line 53), add:

```python
# Session intention
self._session_intention: str = ""
self._intention_bar: IntentionBar | None = None
```

- [ ] **Step 3: Modify `_on_start()` to show popup**

Replace the `_on_start` method. The key change: when `_session_active` is False and timer is IDLE, show the intention popup instead of immediately starting. The popup's callback then starts the session.

```python
def _on_start(self) -> None:
    """Handle start/resume/skip-break button click."""
    if self.timer.state == TimerState.IDLE:
        if not self._session_active:
            # New session — ask for intention first
            IntentionPopup(self.root, self._start_session_with_intention)
            return
        self.timer.start_work()
        self._update_sets_display()
    elif self.timer.state == TimerState.PAUSED:
        self.timer.resume()
    elif self.timer.state == TimerState.BREAK:
        print("Break skipped")
        self.timer.skip()
```

- [ ] **Step 4: Add `_start_session_with_intention()` callback**

Add this new method to `ProductivityApp`:

```python
def _start_session_with_intention(self, intention: str) -> None:
    """Called after intention popup submits/skips. Starts the session."""
    self._session_active = True
    self._sets_completed = 0
    self._session_intention = intention
    print(f"Session started: 0/{self.config.sets_per_session} sets")
    if intention:
        print(f"Intention: {intention}")

    # Show intention on timer window
    self.main_window.set_intention(intention)

    # Create top-of-screen bar if intention is set
    if intention:
        self._intention_bar = IntentionBar(self.root, intention)

    self.timer.start_work()
    self._update_sets_display()
```

- [ ] **Step 5: Add cleanup in `_do_stop()`**

In `_do_stop()`, after the existing `self._sets_completed = 0` line, add:

```python
# Clear intention
self._session_intention = ""
self.main_window.clear_intention()
if self._intention_bar is not None:
    self._intention_bar.destroy()
    self._intention_bar = None
```

- [ ] **Step 6: Commit**

```bash
git add src/app.py
git commit -m "feat: integrate intention popup and bar into session lifecycle"
```

---

## Chunk 2: Mac Platform Port

### Task 5: Copy UI components to Mac

**Files:**
- Create: `productivity-mac/src/ui/intention_popup.py`
- Create: `productivity-mac/src/ui/intention_bar.py`

- [ ] **Step 1: Copy IntentionPopup to Mac**

Copy `src/ui/intention_popup.py` to `productivity-mac/src/ui/intention_popup.py`. File is identical.

- [ ] **Step 2: Copy IntentionBar to Mac**

Copy `src/ui/intention_bar.py` to `productivity-mac/src/ui/intention_bar.py`. File is identical.

- [ ] **Step 3: Commit**

```bash
git add productivity-mac/src/ui/intention_popup.py productivity-mac/src/ui/intention_bar.py
git commit -m "feat: add intention popup and bar to Mac version"
```

---

### Task 6: Add intention label to Mac MainWindow

**Files:**
- Modify: `productivity-mac/src/ui/main_window.py`

- [ ] **Step 1: Add intention label and methods**

Same changes as Task 3 — add the `intention_label` after `state_label.pack()`, and add `set_intention()` / `clear_intention()` methods.

- [ ] **Step 2: Commit**

```bash
git add productivity-mac/src/ui/main_window.py
git commit -m "feat: add intention label to Mac timer window"
```

---

### Task 7: Integrate into Mac ProductivityApp

**Files:**
- Modify: `productivity-mac/src/app.py`

- [ ] **Step 1: Add imports**

```python
from src.ui.intention_popup import IntentionPopup
from src.ui.intention_bar import IntentionBar
```

- [ ] **Step 2: Add state fields in `__init__`**

After the `self._is_blocking = False` line, add:

```python
self._session_intention: str = ""
self._intention_bar: IntentionBar | None = None
```

- [ ] **Step 3: Modify `_on_start()`**

Same pattern as Task 4 Step 3. Replace the IDLE + not `_session_active` block to show popup first.

```python
def _on_start(self) -> None:
    """Handle start/resume/skip-break button click."""
    if self.timer.state == TimerState.IDLE:
        if not self._session_active:
            IntentionPopup(self.root, self._start_session_with_intention)
            return
        self.timer.start_work()
        self._update_sets_display()
        self._save_session_state()
    elif self.timer.state == TimerState.PAUSED:
        self.timer.resume()
    elif self.timer.state == TimerState.BREAK:
        print("Break skipped")
        self.timer.skip()
```

- [ ] **Step 4: Add `_start_session_with_intention()` callback**

Same as Task 4 Step 4, but include Mac-specific calls:

```python
def _start_session_with_intention(self, intention: str) -> None:
    """Called after intention popup submits/skips. Starts the session."""
    self._session_active = True
    self._sets_completed = 0
    self._session_intention = intention
    self.tray_icon.set_session_active(True)
    print(f"Session started: 0/{self.config.sets_per_session} sets")
    if intention:
        print(f"Intention: {intention}")

    self.main_window.set_intention(intention)

    if intention:
        self._intention_bar = IntentionBar(self.root, intention)

    self.timer.start_work()
    self._update_sets_display()
    self._save_session_state()
```

- [ ] **Step 5: Add cleanup in `_do_stop()`**

In `_do_stop()`, after the `self._sets_completed = 0` line, add:

```python
self._session_intention = ""
self.main_window.clear_intention()
if self._intention_bar is not None:
    self._intention_bar.destroy()
    self._intention_bar = None
```

- [ ] **Step 6: Commit**

```bash
git add productivity-mac/src/app.py
git commit -m "feat: integrate intention feature into Mac app lifecycle"
```

---

## Chunk 3: Final Push

### Task 8: Push all changes

- [ ] **Step 1: Push to remote**

```bash
git push
```
