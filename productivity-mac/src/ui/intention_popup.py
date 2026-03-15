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
