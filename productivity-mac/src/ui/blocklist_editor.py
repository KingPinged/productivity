"""
Block list editor for managing blocked apps and websites.
"""

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from typing import Callable

from src.data.config import Config
from src.data.default_blocklists import BLOCKED_APPS, BLOCKED_WEBSITES


class BlocklistEditor:
    """
    Dialog for editing blocked apps and websites.
    Allows enabling/disabling categories and adding custom items.
    """

    def __init__(
        self,
        parent: ttk.Window,
        config: Config,
        on_save: Callable[[Config], None],
    ):
        """
        Initialize the blocklist editor.

        Args:
            parent: Parent window
            config: Current configuration
            on_save: Callback when settings are saved
        """
        self.parent = parent
        self.config = config
        self.on_save = on_save

        self._app_category_vars = {}
        self._website_category_vars = {}

        self._setup_dialog()

    def _setup_dialog(self) -> None:
        """Set up the dialog UI."""
        # Create toplevel window
        self.dialog = ttk.Toplevel(self.parent)
        self.dialog.title("Block Lists")
        self.dialog.resizable(True, True)

        # Create notebook for tabs
        notebook = ttk.Notebook(self.dialog)
        notebook.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        # Apps tab
        apps_frame = ttk.Frame(notebook, padding=10)
        notebook.add(apps_frame, text="Applications")
        self._setup_apps_tab(apps_frame)

        # Websites tab
        websites_frame = ttk.Frame(notebook, padding=10)
        notebook.add(websites_frame, text="Websites")
        self._setup_websites_tab(websites_frame)

        # Buttons at bottom
        buttons_frame = ttk.Frame(self.dialog)
        buttons_frame.pack(fill=X, padx=10, pady=(0, 10))

        cancel_btn = ttk.Button(
            buttons_frame,
            text="Cancel",
            command=self.dialog.destroy,
            bootstyle="secondary",
            width=12
        )
        cancel_btn.pack(side=LEFT)

        save_btn = ttk.Button(
            buttons_frame,
            text="Save",
            command=self._on_save,
            bootstyle="success",
            width=12
        )
        save_btn.pack(side=RIGHT)

        # Finalize dialog - MUST be done AFTER all widgets are created
        self.dialog.update_idletasks()

        # Set size and center on parent
        width = 600
        height = 600
        x = self.parent.winfo_x() + (self.parent.winfo_width() - width) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - height) // 2
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")

        # Make modal
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.focus_set()

    def _setup_apps_tab(self, parent: ttk.Frame) -> None:
        """Set up the applications tab."""
        # Categories section
        cat_label = ttk.Label(
            parent,
            text="Application Categories",
            font=("Helvetica", 12, "bold")
        )
        cat_label.pack(anchor=W, pady=(0, 10))

        cat_frame = ttk.Labelframe(parent, text="Enable/Disable Categories", padding=10)
        cat_frame.pack(fill=X, pady=(0, 15))

        for category in BLOCKED_APPS.keys():
            var = ttk.BooleanVar(value=category in self.config.enabled_app_categories)
            self._app_category_vars[category] = var

            check = ttk.Checkbutton(
                cat_frame,
                text=category.replace("_", " ").title(),
                variable=var,
                bootstyle="round-toggle"
            )
            check.pack(anchor=W, pady=2)

            # Show count
            count = len(BLOCKED_APPS[category])
            count_label = ttk.Label(
                cat_frame,
                text=f"   ({count} apps)",
                bootstyle="secondary"
            )
            count_label.pack(anchor=W)

        # Custom apps section
        custom_label = ttk.Label(
            parent,
            text="Custom Blocked Apps",
            font=("Helvetica", 12, "bold")
        )
        custom_label.pack(anchor=W, pady=(15, 10))

        custom_frame = ttk.Frame(parent)
        custom_frame.pack(fill=BOTH, expand=YES)

        # Listbox with scrollbar
        list_frame = ttk.Frame(custom_frame)
        list_frame.pack(fill=BOTH, expand=YES)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=RIGHT, fill=Y)

        self.apps_listbox = ttk.Treeview(
            list_frame,
            columns=("app",),
            show="headings",
            yscrollcommand=scrollbar.set,
            height=5
        )
        self.apps_listbox.heading("app", text="Process Name")
        self.apps_listbox.pack(fill=BOTH, expand=YES)
        scrollbar.config(command=self.apps_listbox.yview)

        # Populate custom apps
        for app in self.config.custom_blocked_apps:
            self.apps_listbox.insert("", END, values=(app,))

        # Add/Remove buttons
        btn_frame = ttk.Frame(custom_frame)
        btn_frame.pack(fill=X, pady=(10, 0))

        self.app_entry = ttk.Entry(btn_frame, width=30)
        self.app_entry.pack(side=LEFT, padx=(0, 5))
        self.app_entry.insert(0, "Example")

        add_btn = ttk.Button(
            btn_frame,
            text="Add",
            command=self._add_custom_app,
            bootstyle="success",
            width=8
        )
        add_btn.pack(side=LEFT, padx=5)

        remove_btn = ttk.Button(
            btn_frame,
            text="Remove",
            command=self._remove_custom_app,
            bootstyle="danger",
            width=8
        )
        remove_btn.pack(side=LEFT, padx=5)

    def _setup_websites_tab(self, parent: ttk.Frame) -> None:
        """Set up the websites tab."""
        # Categories section
        cat_label = ttk.Label(
            parent,
            text="Website Categories",
            font=("Helvetica", 12, "bold")
        )
        cat_label.pack(anchor=W, pady=(0, 10))

        cat_frame = ttk.Labelframe(parent, text="Enable/Disable Categories", padding=10)
        cat_frame.pack(fill=X, pady=(0, 15))

        for category in BLOCKED_WEBSITES.keys():
            var = ttk.BooleanVar(value=category in self.config.enabled_website_categories)
            self._website_category_vars[category] = var

            check = ttk.Checkbutton(
                cat_frame,
                text=category.replace("_", " ").title(),
                variable=var,
                bootstyle="round-toggle"
            )
            check.pack(anchor=W, pady=2)

            # Show count
            count = len(BLOCKED_WEBSITES[category])
            count_label = ttk.Label(
                cat_frame,
                text=f"   ({count} sites)",
                bootstyle="secondary"
            )
            count_label.pack(anchor=W)

        # Custom websites section
        custom_label = ttk.Label(
            parent,
            text="Custom Blocked Websites",
            font=("Helvetica", 12, "bold")
        )
        custom_label.pack(anchor=W, pady=(15, 10))

        custom_frame = ttk.Frame(parent)
        custom_frame.pack(fill=BOTH, expand=YES)

        # Listbox with scrollbar
        list_frame = ttk.Frame(custom_frame)
        list_frame.pack(fill=BOTH, expand=YES)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=RIGHT, fill=Y)

        self.websites_listbox = ttk.Treeview(
            list_frame,
            columns=("site",),
            show="headings",
            yscrollcommand=scrollbar.set,
            height=5
        )
        self.websites_listbox.heading("site", text="Domain")
        self.websites_listbox.pack(fill=BOTH, expand=YES)
        scrollbar.config(command=self.websites_listbox.yview)

        # Populate custom websites
        for site in self.config.custom_blocked_websites:
            self.websites_listbox.insert("", END, values=(site,))

        # Add/Remove buttons
        btn_frame = ttk.Frame(custom_frame)
        btn_frame.pack(fill=X, pady=(10, 0))

        self.website_entry = ttk.Entry(btn_frame, width=30)
        self.website_entry.pack(side=LEFT, padx=(0, 5))
        self.website_entry.insert(0, "example.com")

        add_btn = ttk.Button(
            btn_frame,
            text="Add",
            command=self._add_custom_website,
            bootstyle="success",
            width=8
        )
        add_btn.pack(side=LEFT, padx=5)

        remove_btn = ttk.Button(
            btn_frame,
            text="Remove",
            command=self._remove_custom_website,
            bootstyle="danger",
            width=8
        )
        remove_btn.pack(side=LEFT, padx=5)

    def _add_custom_app(self) -> None:
        """Add a custom app to the blocklist."""
        app = self.app_entry.get().strip()
        if app:
            self.apps_listbox.insert("", END, values=(app,))
            self.app_entry.delete(0, END)

    def _remove_custom_app(self) -> None:
        """Remove selected custom app from the blocklist."""
        selected = self.apps_listbox.selection()
        for item in selected:
            self.apps_listbox.delete(item)

    def _add_custom_website(self) -> None:
        """Add a custom website to the blocklist."""
        site = self.website_entry.get().strip()
        if site and "." in site:
            # Remove protocol if present
            site = site.replace("https://", "").replace("http://", "")
            site = site.rstrip("/")
            self.websites_listbox.insert("", END, values=(site,))
            self.website_entry.delete(0, END)

    def _remove_custom_website(self) -> None:
        """Remove selected custom website from the blocklist."""
        selected = self.websites_listbox.selection()
        for item in selected:
            self.websites_listbox.delete(item)

    def _on_save(self) -> None:
        """Handle save button click."""
        # Update enabled app categories
        self.config.enabled_app_categories = [
            cat for cat, var in self._app_category_vars.items() if var.get()
        ]

        # Update enabled website categories
        self.config.enabled_website_categories = [
            cat for cat, var in self._website_category_vars.items() if var.get()
        ]

        # Update custom apps
        self.config.custom_blocked_apps = [
            self.apps_listbox.item(item)["values"][0]
            for item in self.apps_listbox.get_children()
        ]

        # Update custom websites
        self.config.custom_blocked_websites = [
            self.websites_listbox.item(item)["values"][0]
            for item in self.websites_listbox.get_children()
        ]

        # Save config to file
        self.config.save()

        # Notify callback
        self.on_save(self.config)

        # Close dialog
        self.dialog.destroy()
