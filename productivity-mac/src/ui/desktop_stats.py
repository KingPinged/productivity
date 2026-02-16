"""
Desktop Stats Widget - Displays productivity stats as a floating window (macOS).
Uses a simple topmost Tkinter window instead of Windows WorkerW embedding.
"""

import threading
import time
import tkinter as tk
from typing import Optional, Callable
from dataclasses import dataclass


@dataclass
class StatsData:
    """Data structure for stats display."""
    hours_worked_today: float = 0.0
    hours_worked_total: float = 0.0
    cycles_today: int = 0
    cycles_total: int = 0
    seconds_since_adult_access: Optional[int] = None
    work_minutes: int = 52
    session_history: list = None  # List of dicts with date, cycles, minutes
    percentage_change: tuple = None  # (percentage, is_increase)
    top_apps_today: list = None  # List of (name, seconds) tuples
    top_websites_today: list = None  # List of (name, seconds) tuples

    def __post_init__(self):
        if self.session_history is None:
            self.session_history = []
        if self.percentage_change is None:
            self.percentage_change = (0.0, True)
        if self.top_apps_today is None:
            self.top_apps_today = []
        if self.top_websites_today is None:
            self.top_websites_today = []


class DesktopStatsWidget:
    """
    Desktop widget that displays productivity stats as a floating window.
    Shows hours worked and time since last adult site access.
    """

    def __init__(
        self,
        get_stats_callback: Callable[[], StatsData],
        update_interval_ms: int = 1000
    ):
        """
        Initialize the desktop stats widget.

        Args:
            get_stats_callback: Function that returns current StatsData
            update_interval_ms: How often to update display (default 1 second)
        """
        self.get_stats = get_stats_callback
        self.update_interval = update_interval_ms
        self.root: Optional[tk.Tk] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _format_duration(self, total_seconds: int) -> str:
        """Format seconds into Days:Hours:Minutes:Seconds format."""
        if total_seconds < 0:
            return "0:00:00:00"

        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        return f"{days}:{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _format_usage_time(self, seconds: int) -> str:
        """Format seconds as short human-readable time for usage display."""
        if seconds < 60:
            return f"{seconds}s"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60

        if hours > 0:
            return f"{hours}h{minutes}m" if minutes > 0 else f"{hours}h"
        return f"{minutes}m"

    def _create_window(self):
        """Create the Tkinter window as a simple topmost floating widget."""
        self.root = tk.Tk()
        self.root.title("ProductivityStats")

        # Remove window decorations
        self.root.overrideredirect(True)

        # Set window size and position (top-left corner with padding)
        width = 380
        height = 270
        x = 20
        y = 20
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        # Make window background transparent
        self.root.configure(bg='black')
        self.root.attributes('-transparentcolor', 'black')

        # Keep on top initially, then allow other windows to overlap
        self.root.attributes('-topmost', True)

        # Create main frame with semi-transparent background effect
        self.frame = tk.Frame(self.root, bg='#1a1a1a', highlightthickness=0)
        self.frame.pack(fill='both', expand=True, padx=5, pady=5)

        # Stats labels with modern styling
        font_large = ('Helvetica Neue', 14, 'bold')
        font_small = ('Helvetica Neue', 10)
        font_tiny = ('Helvetica Neue', 8)
        fg_color = '#00ff88'  # Green accent color
        fg_secondary = '#888888'

        # Top row: Hours and percentage change
        top_row = tk.Frame(self.frame, bg='#1a1a1a')
        top_row.pack(fill='x', padx=10, pady=(10, 2))

        # Hours worked label
        self.hours_label = tk.Label(
            top_row,
            text="Hours Today: 0.0h",
            font=font_large,
            fg=fg_color,
            bg='#1a1a1a',
            anchor='w'
        )
        self.hours_label.pack(side='left')

        # Percentage change indicator
        self.change_label = tk.Label(
            top_row,
            text="",
            font=font_small,
            fg='#00ff88',
            bg='#1a1a1a',
            anchor='e'
        )
        self.change_label.pack(side='right')

        # Total hours sublabel
        self.total_label = tk.Label(
            self.frame,
            text="Total: 0.0h (0 sessions)",
            font=font_small,
            fg=fg_secondary,
            bg='#1a1a1a',
            anchor='w'
        )
        self.total_label.pack(fill='x', padx=10, pady=(0, 5))

        # Time since clean label with larger format
        self.clean_label = tk.Label(
            self.frame,
            text="Clean: 0:00:00:00",
            font=font_large,
            fg='#00aaff',  # Blue accent
            bg='#1a1a1a',
            anchor='w'
        )
        self.clean_label.pack(fill='x', padx=10, pady=(5, 5))

        # Bar graph section
        graph_frame = tk.Frame(self.frame, bg='#1a1a1a')
        graph_frame.pack(fill='x', padx=10, pady=(5, 5))

        # Graph title
        graph_title = tk.Label(
            graph_frame,
            text="Weekly Sessions",
            font=font_small,
            fg=fg_secondary,
            bg='#1a1a1a',
            anchor='w'
        )
        graph_title.pack(fill='x')

        # Canvas for bar graph
        self.graph_canvas = tk.Canvas(
            graph_frame,
            width=350,
            height=70,
            bg='#1a1a1a',
            highlightthickness=0
        )
        self.graph_canvas.pack(fill='x', pady=(2, 0))

        # Day labels frame
        self.day_labels_frame = tk.Frame(graph_frame, bg='#1a1a1a')
        self.day_labels_frame.pack(fill='x')

        # Create day label widgets
        self.day_labels = []
        days_of_week = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
        for i in range(7):
            lbl = tk.Label(
                self.day_labels_frame,
                text=days_of_week[i],
                font=font_tiny,
                fg=fg_secondary,
                bg='#1a1a1a',
                width=5
            )
            lbl.pack(side='left', expand=True)
            self.day_labels.append(lbl)

        # Usage summary label
        self.usage_label = tk.Label(
            self.frame,
            text="",
            font=font_tiny,
            fg='#888888',
            bg='#1a1a1a',
            anchor='w'
        )
        self.usage_label.pack(fill='x', padx=10, pady=(5, 0))

        # Allow the topmost to drop after initial display so other windows can cover
        self.root.after(100, lambda: self.root.attributes('-topmost', False))

        # Start periodic visibility refresh
        self._refresh_visibility()

        # Start update loop
        self._update_display()

    def _refresh_visibility(self):
        """Periodically refresh window visibility."""
        if not self._running or not self.root:
            return

        try:
            # Briefly set topmost then remove - brings window forward if hidden
            self.root.attributes('-topmost', True)
            self.root.after(50, lambda: self.root.attributes('-topmost', False))
        except Exception:
            pass

        # Schedule next visibility refresh (every 5 seconds)
        if self._running and self.root:
            self.root.after(5000, self._refresh_visibility)

    def _update_display(self):
        """Update the stats display."""
        if not self._running or not self.root:
            return

        try:
            stats = self.get_stats()

            # Calculate hours
            hours_today = (stats.cycles_today * stats.work_minutes) / 60
            hours_total = (stats.cycles_total * stats.work_minutes) / 60

            # Update hours label
            self.hours_label.config(text=f"Hours Today: {hours_today:.1f}h")
            self.total_label.config(
                text=f"Total: {hours_total:.1f}h ({stats.cycles_total} sessions)"
            )

            # Update percentage change indicator
            if stats.percentage_change:
                pct, is_increase = stats.percentage_change
                if pct > 0:
                    arrow = "\u2191" if is_increase else "\u2193"  # up or down
                    color = '#00ff88' if is_increase else '#ff6666'
                    self.change_label.config(text=f"{arrow} {pct:.0f}%", fg=color)
                else:
                    self.change_label.config(text="--", fg='#888888')

            # Update clean time label
            if stats.seconds_since_adult_access is not None and stats.seconds_since_adult_access > 0:
                clean_time = self._format_duration(stats.seconds_since_adult_access)
                self.clean_label.config(text=f"Clean: {clean_time}")

                # Color coding based on duration
                if stats.seconds_since_adult_access >= 86400 * 7:  # 7+ days
                    self.clean_label.config(fg='#00ff00')  # Bright green
                elif stats.seconds_since_adult_access >= 86400:  # 1+ days
                    self.clean_label.config(fg='#00ff88')  # Green
                elif stats.seconds_since_adult_access >= 3600:  # 1+ hours
                    self.clean_label.config(fg='#ffaa00')  # Orange
                else:
                    self.clean_label.config(fg='#ff4444')  # Red
            else:
                self.clean_label.config(text="Clean: 0:00:00:00", fg='#00aaff')

            # Update bar graph
            self._draw_bar_graph(stats.session_history)

            # Update usage summary
            self._update_usage_summary(stats)

        except Exception as e:
            print(f"Error updating desktop stats: {e}")

        # Schedule next update
        if self._running and self.root:
            self.root.after(self.update_interval, self._update_display)

    def _update_usage_summary(self, stats: StatsData) -> None:
        """Update the usage summary label with top apps/websites."""
        if not hasattr(self, 'usage_label'):
            return

        parts = []

        # Add top app
        if stats.top_apps_today:
            name, seconds = stats.top_apps_today[0]
            display_name = name[:12]
            parts.append(f"{display_name} ({self._format_usage_time(seconds)})")

        # Add top website
        if stats.top_websites_today:
            name, seconds = stats.top_websites_today[0]
            display_name = name[:15] if len(name) > 15 else name
            parts.append(f"{display_name} ({self._format_usage_time(seconds)})")

        if parts:
            self.usage_label.config(text="Top: " + ", ".join(parts))
        else:
            self.usage_label.config(text="")

    def _draw_bar_graph(self, session_history: list):
        """Draw the weekly session bar graph."""
        if not hasattr(self, 'graph_canvas') or not self.graph_canvas:
            return

        # Clear canvas
        self.graph_canvas.delete('all')

        canvas_width = 350
        canvas_height = 70
        bar_count = 7
        bar_spacing = 8
        bar_width = (canvas_width - (bar_count + 1) * bar_spacing) // bar_count
        max_height = canvas_height - 15  # Leave room for value labels

        # Get max cycles for scaling
        if session_history:
            max_cycles = max((h['cycles'] for h in session_history), default=1)
        else:
            max_cycles = 1
        if max_cycles == 0:
            max_cycles = 1

        # Draw bars
        for i, day_data in enumerate(session_history[-7:]):  # Last 7 days
            cycles = day_data.get('cycles', 0)

            # Calculate bar dimensions
            x1 = bar_spacing + i * (bar_width + bar_spacing)
            x2 = x1 + bar_width

            # Scale height (minimum 3px if cycles > 0 for visibility)
            if cycles > 0:
                bar_height = max(3, int((cycles / max_cycles) * max_height))
            else:
                bar_height = 0

            y2 = canvas_height - 2
            y1 = y2 - bar_height

            # Color gradient based on performance (today is highlighted)
            is_today = (i == len(session_history) - 1)
            if is_today:
                color = '#00ff88'  # Bright green for today
            elif cycles > 0:
                intensity = cycles / max_cycles
                if intensity > 0.7:
                    color = '#00cc66'
                elif intensity > 0.4:
                    color = '#88aa44'
                else:
                    color = '#aa8822'
            else:
                color = '#333333'  # Dark gray for no data

            # Draw bar
            if bar_height > 0:
                self.graph_canvas.create_rectangle(
                    x1, y1, x2, y2,
                    fill=color,
                    outline='',
                    tags='bar'
                )

            # Draw cycle count above bar
            if cycles > 0:
                self.graph_canvas.create_text(
                    (x1 + x2) // 2,
                    y1 - 6,
                    text=str(cycles),
                    fill='#aaaaaa',
                    font=('Helvetica Neue', 7),
                    anchor='s'
                )

        # Update day labels based on actual dates
        if session_history and hasattr(self, 'day_labels'):
            from datetime import datetime
            for i, day_data in enumerate(session_history[-7:]):
                date_str = day_data.get('date', '')
                try:
                    dt = datetime.fromisoformat(date_str)
                    day_abbr = dt.strftime('%a')[0]  # First letter of day name
                    self.day_labels[i].config(text=day_abbr)
                except (ValueError, IndexError):
                    pass

    def _run_mainloop(self):
        """Run the Tkinter main loop in a separate thread."""
        try:
            self._create_window()
            self.root.mainloop()
        except Exception as e:
            print(f"Desktop stats widget error: {e}")
        finally:
            self._running = False

    def start(self):
        """Start the desktop stats widget."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_mainloop, daemon=True)
        self._thread.start()
        print("Desktop stats widget started")

    def stop(self):
        """Stop the desktop stats widget."""
        self._running = False
        if self.root:
            try:
                self.root.after(0, self.root.destroy)
            except Exception:
                pass
        self.root = None
        print("Desktop stats widget stopped")

    def is_running(self) -> bool:
        """Check if the widget is running."""
        return self._running
