"""
Usage Statistics Window - Displays app and website usage data with visualizations.
"""

import csv
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime
from typing import Callable, List, Tuple, Optional

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from src.data.usage_data import UsageData


class UsageStatsWindow:
    """
    Window for displaying usage statistics with bar charts.
    Shows top apps and websites by time spent.
    """

    def __init__(
        self,
        parent: tk.Tk,
        usage_data: UsageData,
        on_close: Optional[Callable] = None,
    ):
        """
        Initialize the usage stats window.

        Args:
            parent: Parent window
            usage_data: UsageData instance with tracking data
            on_close: Optional callback when window closes
        """
        self.parent = parent
        self.usage_data = usage_data
        self.on_close = on_close
        self.current_period = 'today'
        self._resize_after_id = None  # For debouncing resize events

        # Create window
        self.window = ttk.Toplevel(parent)
        self.window.title("Usage Statistics")
        self.window.resizable(True, True)
        self.window.minsize(600, 450)

        # Handle close
        self.window.protocol("WM_DELETE_WINDOW", self._close)

        # Build UI - MUST be done before setting geometry
        self._build_ui()

        # Finalize dialog - MUST be done AFTER all widgets are created
        self.window.update_idletasks()

        # Set size and center on parent
        width = 700
        height = 550
        x = parent.winfo_x() + (parent.winfo_width() - width) // 2
        y = parent.winfo_y() + (parent.winfo_height() - height) // 2
        self.window.geometry(f"{width}x{height}+{x}+{y}")

        # Make modal
        self.window.transient(parent)
        self.window.grab_set()
        self.window.focus_set()

        # Load initial data AFTER window is fully laid out
        # Use after() to ensure canvas has proper dimensions
        self.window.after(50, self._refresh_data)

    def _build_ui(self) -> None:
        """Build the user interface."""
        # Main container with padding
        main_frame = ttk.Frame(self.window, padding=15)
        main_frame.pack(fill=BOTH, expand=True)

        # Title
        title_label = ttk.Label(
            main_frame,
            text="Usage Statistics",
            font=("Helvetica", 18, "bold"),
        )
        title_label.pack(pady=(0, 15))

        # Period selection buttons
        period_frame = ttk.Frame(main_frame)
        period_frame.pack(fill=X, pady=(0, 15))

        self.period_buttons = {}
        for period, label in [('today', 'Today'), ('week', 'This Week'), ('all_time', 'All Time')]:
            btn = ttk.Button(
                period_frame,
                text=label,
                command=lambda p=period: self._select_period(p),
                bootstyle="outline" if period != self.current_period else "primary",
                width=12,
            )
            btn.pack(side=LEFT, padx=5)
            self.period_buttons[period] = btn

        # Content frame with two columns
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=BOTH, expand=True)

        # Configure grid
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=1)
        content_frame.rowconfigure(0, weight=1)

        # Apps column
        apps_frame = ttk.Labelframe(content_frame, text="Applications", padding=10)
        apps_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        self.apps_total_label = ttk.Label(
            apps_frame,
            text="Total: 0h 0m",
            font=("Helvetica", 10),
        )
        self.apps_total_label.pack(anchor=W, pady=(0, 5))

        self.apps_canvas = tk.Canvas(
            apps_frame,
            bg='#2b2b2b',
            highlightthickness=0,
            width=280,
            height=350,
        )
        self.apps_canvas.pack(fill=BOTH, expand=True)

        # Websites column
        websites_frame = ttk.Labelframe(content_frame, text="Websites", padding=10)
        websites_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        self.websites_total_label = ttk.Label(
            websites_frame,
            text="Total: 0h 0m",
            font=("Helvetica", 10),
        )
        self.websites_total_label.pack(anchor=W, pady=(0, 5))

        self.websites_canvas = tk.Canvas(
            websites_frame,
            bg='#2b2b2b',
            highlightthickness=0,
            width=280,
            height=350,
        )
        self.websites_canvas.pack(fill=BOTH, expand=True)

        # Bottom buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=X, pady=(15, 0))

        export_btn = ttk.Button(
            button_frame,
            text="Export CSV",
            command=self._export_csv,
            bootstyle="info-outline",
        )
        export_btn.pack(side=LEFT)

        refresh_btn = ttk.Button(
            button_frame,
            text="Refresh",
            command=self._refresh_data,
            bootstyle="secondary-outline",
        )
        refresh_btn.pack(side=LEFT, padx=10)

        close_btn = ttk.Button(
            button_frame,
            text="Close",
            command=self._close,
            bootstyle="secondary",
        )
        close_btn.pack(side=RIGHT)

        # Bind resize event with debouncing to prevent excessive redraws
        self.apps_canvas.bind('<Configure>', lambda e: self._on_resize())
        self.websites_canvas.bind('<Configure>', lambda e: self._on_resize())

    def _on_resize(self) -> None:
        """Handle resize event with debouncing."""
        # Cancel any pending refresh
        if self._resize_after_id:
            self.window.after_cancel(self._resize_after_id)
        # Schedule refresh after a short delay
        self._resize_after_id = self.window.after(100, self._refresh_data)

    def _select_period(self, period: str) -> None:
        """Handle period selection."""
        self.current_period = period

        # Update button styles
        for p, btn in self.period_buttons.items():
            if p == period:
                btn.configure(bootstyle="primary")
            else:
                btn.configure(bootstyle="outline")

        self._refresh_data()

    def _format_time(self, seconds: int) -> str:
        """Format seconds as human-readable time."""
        if seconds < 60:
            return f"{seconds}s"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60

        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def _format_time_short(self, seconds: int) -> str:
        """Format seconds as short human-readable time."""
        if seconds < 60:
            return f"{seconds}s"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60

        if hours > 0:
            if minutes > 0:
                return f"{hours}h{minutes}m"
            return f"{hours}h"
        return f"{minutes}m"

    def _draw_bar_chart(
        self,
        canvas: tk.Canvas,
        items: List[Tuple[str, int]],
        max_items: int = 10,
    ) -> None:
        """
        Draw a horizontal bar chart on the canvas.

        Args:
            canvas: Canvas widget to draw on
            items: List of (name, seconds) tuples
            max_items: Maximum items to display
        """
        canvas.delete('all')

        canvas.update_idletasks()
        width = canvas.winfo_width()
        height = canvas.winfo_height()

        if width <= 1 or height <= 1:
            return

        # Limit items
        items = items[:max_items]

        if not items:
            # Show "No data" message
            canvas.create_text(
                width // 2,
                height // 2,
                text="No data yet",
                fill='#666666',
                font=('Segoe UI', 12),
            )
            return

        # Layout constants
        padding = 10
        bar_height = 25
        bar_spacing = 8
        label_width = 120
        time_width = 60

        # Calculate bar area
        bar_start_x = padding + label_width
        bar_end_x = width - padding - time_width - 10
        bar_max_width = bar_end_x - bar_start_x

        if bar_max_width < 50:
            bar_max_width = 50

        # Find max value for scaling
        max_seconds = max(s for _, s in items) if items else 1
        if max_seconds == 0:
            max_seconds = 1

        # Colors for bars
        colors = [
            '#00ff88',  # Green (top)
            '#00cc66',
            '#00aa55',
            '#008844',
            '#006633',
            '#555555',
            '#444444',
            '#3a3a3a',
            '#333333',
            '#2d2d2d',
        ]

        y = padding

        for i, (name, seconds) in enumerate(items):
            if y + bar_height > height - padding:
                break

            # Calculate bar width
            bar_width = int((seconds / max_seconds) * bar_max_width)
            bar_width = max(bar_width, 3)  # Minimum width

            # Get color
            color = colors[min(i, len(colors) - 1)]

            # Draw label (truncate if needed)
            display_name = name
            if len(display_name) > 15:
                display_name = display_name[:14] + '...'

            canvas.create_text(
                padding,
                y + bar_height // 2,
                text=display_name,
                fill='#cccccc',
                font=('Segoe UI', 9),
                anchor='w',
            )

            # Draw bar
            canvas.create_rectangle(
                bar_start_x,
                y + 2,
                bar_start_x + bar_width,
                y + bar_height - 2,
                fill=color,
                outline='',
            )

            # Draw time label
            time_text = self._format_time_short(seconds)
            canvas.create_text(
                bar_end_x + 10,
                y + bar_height // 2,
                text=time_text,
                fill='#aaaaaa',
                font=('Segoe UI', 9),
                anchor='w',
            )

            y += bar_height + bar_spacing

    def _refresh_data(self) -> None:
        """Refresh the displayed data."""
        # Get top items for current period
        apps = self.usage_data.get_top_items('app', self.current_period, limit=10)
        websites = self.usage_data.get_top_items('website', self.current_period, limit=10)

        # Get totals
        app_total = self.usage_data.get_total_time('app', self.current_period)
        website_total = self.usage_data.get_total_time('website', self.current_period)

        # Update total labels
        self.apps_total_label.config(text=f"Total: {self._format_time(app_total)}")
        self.websites_total_label.config(text=f"Total: {self._format_time(website_total)}")

        # Draw charts
        self._draw_bar_chart(self.apps_canvas, apps)
        self._draw_bar_chart(self.websites_canvas, websites)

    def _export_csv(self) -> None:
        """Export usage data to CSV file."""
        # Ask for file location
        filename = filedialog.asksaveasfilename(
            parent=self.window,
            defaultextension='.csv',
            filetypes=[('CSV files', '*.csv'), ('All files', '*.*')],
            initialfilename=f'usage_export_{datetime.now().strftime("%Y%m%d")}.csv',
        )

        if not filename:
            return

        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Header
                writer.writerow(['Category', 'Name', 'Today (seconds)', 'This Week (seconds)', 'All Time (seconds)'])

                # Get all unique items
                all_items = set()

                for period in ['today', 'week', 'all_time']:
                    for name, _ in self.usage_data.get_top_items('app', period, limit=100):
                        all_items.add(('app', name))
                    for name, _ in self.usage_data.get_top_items('website', period, limit=100):
                        all_items.add(('website', name))

                # Write data for each item
                for category, name in sorted(all_items):
                    today = 0
                    week = 0
                    all_time = 0

                    for n, s in self.usage_data.get_top_items(category, 'today', limit=100):
                        if n == name:
                            today = s
                            break

                    for n, s in self.usage_data.get_top_items(category, 'week', limit=100):
                        if n == name:
                            week = s
                            break

                    for n, s in self.usage_data.get_top_items(category, 'all_time', limit=100):
                        if n == name:
                            all_time = s
                            break

                    writer.writerow([category, name, today, week, all_time])

            messagebox.showinfo(
                "Export Complete",
                f"Usage data exported to:\n{filename}",
                parent=self.window,
            )

        except Exception as e:
            messagebox.showerror(
                "Export Failed",
                f"Could not export data:\n{str(e)}",
                parent=self.window,
            )

    def _close(self) -> None:
        """Close the window."""
        if self.on_close:
            self.on_close()
        self.window.destroy()
