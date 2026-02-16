"""
Persistent cache for AI NSFW detection results.
Stores per-domain classifications so each domain is only checked once.
"""

import json
import threading
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional

from src.utils.constants import NSFW_CACHE_FILE, APP_DATA_DIR


@dataclass
class CacheEntry:
    """Single NSFW classification result for a domain."""
    domain: str
    is_nsfw: bool
    confidence: float
    checked_at: str  # ISO format timestamp
    method: str  # 'moderation', 'llm', or 'error'

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'CacheEntry':
        return cls(
            domain=data['domain'],
            is_nsfw=data['is_nsfw'],
            confidence=data.get('confidence', 0.0),
            checked_at=data.get('checked_at', ''),
            method=data.get('method', 'unknown'),
        )


class NSFWCache:
    """
    Thread-safe persistent cache for NSFW domain classifications.
    Follows the same pattern as UsageData (lock, dirty flag, JSON persistence).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._entries: Dict[str, CacheEntry] = {}
        self._dirty = False

    def get(self, domain: str) -> Optional[CacheEntry]:
        """Get cached classification for a domain."""
        with self._lock:
            return self._entries.get(domain.lower())

    def put(self, entry: CacheEntry) -> None:
        """Store a classification result."""
        with self._lock:
            self._entries[entry.domain.lower()] = entry
            self._dirty = True

    def get_all_nsfw_domains(self) -> List[str]:
        """Get all domains classified as NSFW."""
        with self._lock:
            return [
                entry.domain for entry in self._entries.values()
                if entry.is_nsfw
            ]

    def get_all_entries(self) -> List[CacheEntry]:
        """Get all cached entries."""
        with self._lock:
            return list(self._entries.values())

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
                    domain: entry.to_dict()
                    for domain, entry in self._entries.items()
                }
            }

            try:
                with open(NSFW_CACHE_FILE, 'w') as f:
                    json.dump(data, f, indent=2)
                self._dirty = False
            except Exception as e:
                print(f"Error saving NSFW cache: {e}")

    @classmethod
    def load(cls) -> 'NSFWCache':
        """Load cache from disk."""
        instance = cls()

        if not NSFW_CACHE_FILE.exists():
            return instance

        try:
            with open(NSFW_CACHE_FILE, 'r') as f:
                data = json.load(f)

            for domain, entry_data in data.get('entries', {}).items():
                instance._entries[domain] = CacheEntry.from_dict(entry_data)

        except json.JSONDecodeError as e:
            print(f"Error loading NSFW cache (corrupted file): {e}")
        except Exception as e:
            print(f"Error loading NSFW cache: {e}")

        return instance
