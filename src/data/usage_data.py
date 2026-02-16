"""
Usage data tracking for applications and websites.
Stores daily, weekly, and all-time usage statistics.
"""

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.utils.constants import USAGE_DATA_FILE, APP_DATA_DIR


@dataclass
class UsageEntry:
    """Single usage record for an app or website."""
    name: str
    category: str  # 'app' or 'website'
    seconds: int = 0
    last_active: float = 0.0  # Unix timestamp


@dataclass
class DailyUsage:
    """Usage data for a single day."""
    date: str  # ISO format YYYY-MM-DD
    entries: Dict[str, UsageEntry] = field(default_factory=dict)
    total_app_seconds: int = 0
    total_website_seconds: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'date': self.date,
            'entries': {
                key: {
                    'name': entry.name,
                    'category': entry.category,
                    'seconds': entry.seconds,
                    'last_active': entry.last_active
                }
                for key, entry in self.entries.items()
            },
            'total_app_seconds': self.total_app_seconds,
            'total_website_seconds': self.total_website_seconds
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DailyUsage':
        """Create from dictionary."""
        entries = {}
        for key, entry_data in data.get('entries', {}).items():
            entries[key] = UsageEntry(
                name=entry_data['name'],
                category=entry_data['category'],
                seconds=entry_data.get('seconds', 0),
                last_active=entry_data.get('last_active', 0.0)
            )
        return cls(
            date=data['date'],
            entries=entries,
            total_app_seconds=data.get('total_app_seconds', 0),
            total_website_seconds=data.get('total_website_seconds', 0)
        )


class UsageData:
    """
    Complete usage tracking data store.
    Thread-safe for concurrent access from multiple sources.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._current_date: str = datetime.now().strftime('%Y-%m-%d')
        self._current_day: DailyUsage = DailyUsage(date=self._current_date)
        self._history: Dict[str, DailyUsage] = {}
        self._all_time: Dict[str, int] = {}  # key -> total seconds
        self._dirty = False  # Track if data needs saving

    def _make_key(self, category: str, name: str) -> str:
        """Create a unique key for an entry."""
        return f"{category}:{name}"

    def _check_day_rollover(self) -> None:
        """Check if we need to roll over to a new day."""
        today = datetime.now().strftime('%Y-%m-%d')
        if today != self._current_date:
            # Save current day to history
            if self._current_day.entries:
                self._history[self._current_date] = self._current_day
            # Start new day
            self._current_date = today
            self._current_day = DailyUsage(date=today)
            # Cleanup old history
            self._cleanup_old_history()

    def record_usage(self, name: str, category: str, seconds: int = 1) -> None:
        """
        Record usage for an app or website.
        Thread-safe method called from tracker or extension server.

        Args:
            name: App process name or website domain
            category: 'app' or 'website'
            seconds: Number of seconds to add (default 1)
        """
        with self._lock:
            self._check_day_rollover()

            key = self._make_key(category, name)
            now = datetime.now().timestamp()

            # Update or create entry for current day
            if key in self._current_day.entries:
                entry = self._current_day.entries[key]
                entry.seconds += seconds
                entry.last_active = now
            else:
                self._current_day.entries[key] = UsageEntry(
                    name=name,
                    category=category,
                    seconds=seconds,
                    last_active=now
                )

            # Update daily totals
            if category == 'app':
                self._current_day.total_app_seconds += seconds
            else:
                self._current_day.total_website_seconds += seconds

            # Update all-time totals
            if key in self._all_time:
                self._all_time[key] += seconds
            else:
                self._all_time[key] = seconds

            self._dirty = True

    def get_daily_stats(self, date: str = None) -> DailyUsage:
        """
        Get usage stats for a specific date.

        Args:
            date: ISO format date string, or None for today

        Returns:
            DailyUsage for the requested date
        """
        with self._lock:
            if date is None or date == self._current_date:
                return self._current_day
            return self._history.get(date, DailyUsage(date=date))

    def get_weekly_stats(self) -> List[DailyUsage]:
        """
        Get usage stats for the last 7 days.

        Returns:
            List of DailyUsage objects for last 7 days (oldest first)
        """
        with self._lock:
            result = []
            today = datetime.now()

            for i in range(6, -1, -1):  # 6 days ago to today
                date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
                if date == self._current_date:
                    result.append(self._current_day)
                elif date in self._history:
                    result.append(self._history[date])
                else:
                    result.append(DailyUsage(date=date))

            return result

    def get_all_time_stats(self) -> Dict[str, int]:
        """
        Get all-time usage totals.

        Returns:
            Dictionary mapping keys to total seconds
        """
        with self._lock:
            return self._all_time.copy()

    def get_top_items(
        self,
        category: str,
        period: str = 'today',
        limit: int = 10
    ) -> List[Tuple[str, int]]:
        """
        Get top items by usage time.

        Args:
            category: 'app' or 'website'
            period: 'today', 'week', or 'all_time'
            limit: Maximum number of items to return

        Returns:
            List of (name, seconds) tuples, sorted by seconds descending
        """
        with self._lock:
            if period == 'today':
                entries = self._current_day.entries
                totals = {}
                for key, entry in entries.items():
                    if entry.category == category:
                        totals[entry.name] = entry.seconds
            elif period == 'week':
                totals = {}
                today = datetime.now()
                for i in range(7):
                    date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
                    if date == self._current_date:
                        day_data = self._current_day
                    else:
                        day_data = self._history.get(date)

                    if day_data:
                        for key, entry in day_data.entries.items():
                            if entry.category == category:
                                if entry.name in totals:
                                    totals[entry.name] += entry.seconds
                                else:
                                    totals[entry.name] = entry.seconds
            else:  # all_time
                totals = {}
                prefix = f"{category}:"
                for key, seconds in self._all_time.items():
                    if key.startswith(prefix):
                        name = key[len(prefix):]
                        totals[name] = seconds

            # Sort by seconds descending and limit
            sorted_items = sorted(totals.items(), key=lambda x: x[1], reverse=True)
            return sorted_items[:limit]

    def get_total_time(self, category: str, period: str = 'today') -> int:
        """
        Get total time for a category.

        Args:
            category: 'app' or 'website'
            period: 'today', 'week', or 'all_time'

        Returns:
            Total seconds
        """
        with self._lock:
            if period == 'today':
                if category == 'app':
                    return self._current_day.total_app_seconds
                return self._current_day.total_website_seconds
            elif period == 'week':
                total = 0
                today = datetime.now()
                for i in range(7):
                    date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
                    if date == self._current_date:
                        day_data = self._current_day
                    else:
                        day_data = self._history.get(date)

                    if day_data:
                        if category == 'app':
                            total += day_data.total_app_seconds
                        else:
                            total += day_data.total_website_seconds
                return total
            else:  # all_time
                prefix = f"{category}:"
                return sum(
                    seconds for key, seconds in self._all_time.items()
                    if key.startswith(prefix)
                )

    def _cleanup_old_history(self, days_to_keep: int = 90) -> None:
        """Remove history entries older than specified days."""
        cutoff = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d')
        old_keys = [date for date in self._history.keys() if date < cutoff]
        for key in old_keys:
            del self._history[key]

    def save(self) -> None:
        """Save usage data to disk."""
        with self._lock:
            if not self._dirty:
                return

            # Ensure directory exists
            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

            data = {
                'current_date': self._current_date,
                'current_day': self._current_day.to_dict(),
                'history': {
                    date: day.to_dict()
                    for date, day in self._history.items()
                },
                'all_time': self._all_time
            }

            try:
                with open(USAGE_DATA_FILE, 'w') as f:
                    json.dump(data, f, indent=2)
                self._dirty = False
            except Exception as e:
                print(f"Error saving usage data: {e}")

    @classmethod
    def load(cls) -> 'UsageData':
        """Load usage data from disk."""
        instance = cls()

        if not USAGE_DATA_FILE.exists():
            return instance

        try:
            with open(USAGE_DATA_FILE, 'r') as f:
                data = json.load(f)

            instance._current_date = data.get('current_date', instance._current_date)
            instance._all_time = data.get('all_time', {})

            # Load current day
            if 'current_day' in data:
                instance._current_day = DailyUsage.from_dict(data['current_day'])

            # Load history
            for date, day_data in data.get('history', {}).items():
                instance._history[date] = DailyUsage.from_dict(day_data)

            # Check for day rollover
            instance._check_day_rollover()

        except json.JSONDecodeError as e:
            print(f"Error loading usage data (corrupted file): {e}")
        except Exception as e:
            print(f"Error loading usage data: {e}")

        return instance

    def is_dirty(self) -> bool:
        """Check if data has unsaved changes."""
        return self._dirty
