"""
Persistent cache for AI productivity classification results.
Stores per-app/domain classifications so each is only checked once.
"""

import json
import threading
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Optional

from src.utils.constants import PRODUCTIVITY_CACHE_FILE, APP_DATA_DIR


@dataclass
class ProductivityCacheEntry:
    """Single productivity classification result."""
    name: str  # app name or domain
    is_productive: bool
    confidence: float
    method: str  # 'known_list', 'ai', 'browser_skip', 'error'
    classified_at: str  # ISO format timestamp

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'ProductivityCacheEntry':
        return cls(
            name=data['name'],
            is_productive=data['is_productive'],
            confidence=data.get('confidence', 0.0),
            method=data.get('method', 'unknown'),
            classified_at=data.get('classified_at', ''),
        )


class ProductivityCache:
    """
    Thread-safe persistent cache for productivity classifications.
    Same pattern as NSFWCache: lock, dirty flag, JSON persistence.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._entries: Dict[str, ProductivityCacheEntry] = {}
        self._dirty = False

    def get(self, name: str) -> Optional[ProductivityCacheEntry]:
        """Get cached classification for an app or domain."""
        with self._lock:
            return self._entries.get(name.lower())

    def put(self, entry: ProductivityCacheEntry) -> None:
        """Store a classification result."""
        with self._lock:
            self._entries[entry.name.lower()] = entry
            self._dirty = True

    def is_dirty(self) -> bool:
        """Check if cache has unsaved changes."""
        return self._dirty

    def save(self) -> None:
        """Save cache to disk."""
        with self._lock:
            if not self._dirty:
                return

            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

            data = {
                'entries': {
                    key: entry.to_dict()
                    for key, entry in self._entries.items()
                }
            }

            try:
                with open(PRODUCTIVITY_CACHE_FILE, 'w') as f:
                    json.dump(data, f, indent=2)
                self._dirty = False
            except Exception as e:
                print(f"Error saving productivity cache: {e}")

    @classmethod
    def load(cls) -> 'ProductivityCache':
        """Load cache from disk."""
        instance = cls()

        if not PRODUCTIVITY_CACHE_FILE.exists():
            return instance

        try:
            with open(PRODUCTIVITY_CACHE_FILE, 'r') as f:
                data = json.load(f)

            for key, entry_data in data.get('entries', {}).items():
                instance._entries[key] = ProductivityCacheEntry.from_dict(entry_data)

        except json.JSONDecodeError as e:
            print(f"Error loading productivity cache (corrupted file): {e}")
        except Exception as e:
            print(f"Error loading productivity cache: {e}")

        return instance
