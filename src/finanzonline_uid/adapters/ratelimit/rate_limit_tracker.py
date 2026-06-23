"""File-based rate limit tracker for UID verification queries.

Provides tracking of API call frequency with file locking for safe
concurrent access on network drives. Uses sliding window algorithm.

Contents:
    * :class:`RateLimitStatus` - Current rate limit status
    * :class:`RateLimitTracker` - Thread-safe rate limit tracker

System Role:
    Acts as a rate limiting adapter that tracks API calls to FinanzOnline,
    warning users when configured limits are exceeded while ensuring
    data integrity through file locking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import orjson
from filelock import FileLock, Timeout

from finanzonline_uid._datetime_utils import format_iso_datetime, parse_iso_datetime

logger = logging.getLogger(__name__)

_LOCK_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class RateLimitStatus:
    """Current rate limit status information.

    Attributes:
        current_count: Number of API calls within the current window.
        max_queries: Maximum allowed queries in the window.
        window_hours: Duration of the sliding window in hours.
        is_exceeded: True if current_count exceeds max_queries.
    """

    current_count: int
    max_queries: int
    window_hours: float
    is_exceeded: bool


@dataclass(frozen=True, slots=True)
class PerUidRateLimitStatus:
    """Per-UID rate limit status information.

    Tracks how many times a specific UID has been queried within the
    sliding window. The BMF service limits queries to 2 per UID per day.

    Attributes:
        uid: The UID being checked.
        uid_count: Number of queries for this specific UID in the window.
        per_uid_limit: Maximum allowed queries per UID in the window.
        is_uid_exceeded: True if uid_count exceeds per_uid_limit.
    """

    uid: str
    uid_count: int
    per_uid_limit: int
    is_uid_exceeded: bool


@dataclass(frozen=True, slots=True)
class RateLimitEntry:
    """A single rate limit tracking entry.

    Attributes:
        timestamp: When the API call was made (UTC).
        uid: The UID that was queried.
    """

    timestamp: datetime
    uid: str

    def to_dict(self) -> dict[str, str]:
        """Serialize entry to dictionary for JSON storage."""
        return {
            "timestamp": format_iso_datetime(self.timestamp),
            "uid": self.uid,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RateLimitEntry:
        """Deserialize entry from dictionary.

        Args:
            data: Dictionary with 'timestamp' and 'uid' keys.

        Returns:
            RateLimitEntry instance.
        """
        return cls(
            timestamp=parse_iso_datetime(data["timestamp"]),
            uid=str(data.get("uid", "")),
        )


def _is_entry_within_window(entry: RateLimitEntry, window_start: datetime) -> bool:
    """Check if an entry's timestamp is within the sliding window."""
    return entry.timestamp >= window_start


def _cleanup_old_entries(entries: list[RateLimitEntry], window_start: datetime) -> tuple[list[RateLimitEntry], int]:
    """Remove entries older than the window start.

    Returns:
        Tuple of (cleaned entries, number of entries removed).
    """
    original_count = len(entries)
    cleaned = [e for e in entries if _is_entry_within_window(e, window_start)]
    removed_count = original_count - len(cleaned)
    return cleaned, removed_count


_DEFAULT_MAX_RATELIMIT_ENTRIES = 10000
_DEFAULT_PER_UID_LIMIT = 2  # BMF service limit: 2 queries per UID per day


def _trim_oldest_ratelimit_entries(
    entries: list[RateLimitEntry],
    max_entries: int,
) -> tuple[list[RateLimitEntry], int]:
    """Trim oldest entries to stay within max_entries limit.

    Entries are already sorted by timestamp (oldest first in the list).
    Keeps only the newest max_entries.

    Returns:
        Tuple of (trimmed entries, number of entries removed).
    """
    if len(entries) <= max_entries:
        return entries, 0

    # Sort by timestamp (oldest first) and keep newest entries
    sorted_entries = sorted(entries, key=lambda e: e.timestamp)
    entries_to_remove = len(entries) - max_entries
    trimmed = sorted_entries[entries_to_remove:]
    return trimmed, entries_to_remove


def _empty_data() -> dict[str, Any]:
    """Return an empty rate limit data structure."""
    return {"api_calls": [], "metadata": {}}


def _parse_file_content(content: bytes) -> dict[str, Any]:
    """Parse file content into a valid rate limit data structure."""
    if not content:
        return _empty_data()
    loaded = orjson.loads(content)
    if not isinstance(loaded, dict):
        return _empty_data()
    data = cast(dict[str, Any], loaded)
    if "api_calls" not in data:
        data["api_calls"] = []
    if "metadata" not in data:
        data["metadata"] = {}
    return data


def _extract_entries_list(data: dict[str, Any]) -> list[RateLimitEntry]:
    """Extract api_calls list from data as typed RateLimitEntry objects."""
    raw_entries = data.get("api_calls", [])
    if not isinstance(raw_entries, list):
        return []
    entries: list[RateLimitEntry] = []
    for raw in cast(list[dict[str, Any]], raw_entries):
        try:
            entries.append(RateLimitEntry.from_dict(raw))
        except (KeyError, ValueError):
            continue  # Skip malformed entries
    return entries


class RateLimitTracker:
    """File-based rate limit tracker with sliding window.

    Tracks API calls to FinanzOnline in a JSON file with file locking
    for safe concurrent access. Uses a sliding window to count recent
    queries and determine if the rate limit is exceeded. Enforces a
    maximum entry limit to prevent unbounded file growth.

    Also supports per-UID rate limiting to match BMF service limits
    (2 queries per UID per day).

    Attributes:
        ratelimit_file: Path to the rate limit JSON file.
        max_queries: Maximum queries allowed within the window.
        window_hours: Duration of the sliding window in hours.
        max_entries: Maximum number of entries to keep in the file.
        per_uid_limit: Maximum queries per individual UID in the window.

    Example:
        >>> tracker = RateLimitTracker(
        ...     Path("/tmp/rate_limits.json"),
        ...     max_queries=50,
        ...     window_hours=24.0
        ... )
        >>> status = tracker.record_call("DE123456789")
        >>> if status.is_exceeded:
        ...     print(f"Rate limit exceeded: {status.current_count}/{status.max_queries}")
    """

    def __init__(
        self,
        ratelimit_file: Path,
        max_queries: int,
        window_hours: float,
        max_entries: int = _DEFAULT_MAX_RATELIMIT_ENTRIES,
        per_uid_limit: int = _DEFAULT_PER_UID_LIMIT,
    ) -> None:
        """Initialize rate limit tracker.

        Args:
            ratelimit_file: Path to the JSON rate limit file.
            max_queries: Maximum queries allowed in the window.
            window_hours: Duration of the sliding window in hours.
            max_entries: Maximum entries to keep (default 10000). Oldest
                entries are removed when limit is exceeded.
            per_uid_limit: Maximum queries per individual UID (default 2,
                matching BMF service limit).
        """
        self._ratelimit_file = ratelimit_file
        self._max_queries = max_queries
        self._window_hours = window_hours
        self._max_entries = max_entries
        self._per_uid_limit = per_uid_limit
        self._lock_file = ratelimit_file.with_suffix(".lock")

    @property
    def ratelimit_file(self) -> Path:
        """Return the rate limit file path."""
        return self._ratelimit_file

    @property
    def max_queries(self) -> int:
        """Return the maximum queries allowed."""
        return self._max_queries

    @property
    def window_hours(self) -> float:
        """Return the window duration in hours."""
        return self._window_hours

    @property
    def is_enabled(self) -> bool:
        """Check if rate limiting is enabled (max_queries > 0)."""
        return self._max_queries > 0

    @property
    def max_entries(self) -> int:
        """Return the maximum number of rate limit entries."""
        return self._max_entries

    @property
    def per_uid_limit(self) -> int:
        """Return the maximum queries per individual UID."""
        return self._per_uid_limit

    def get_status(self) -> RateLimitStatus:
        """Get current rate limit status without recording a call.

        Returns:
            Current rate limit status with count of queries in window.
        """
        if not self.is_enabled:
            return RateLimitStatus(
                current_count=0,
                max_queries=self._max_queries,
                window_hours=self._window_hours,
                is_exceeded=False,
            )

        try:
            data = self._read_data()
            entries = _extract_entries_list(data)
            window_start = datetime.now(timezone.utc) - timedelta(hours=self._window_hours)
            valid_entries = [e for e in entries if _is_entry_within_window(e, window_start)]
            current_count = len(valid_entries)

            return RateLimitStatus(
                current_count=current_count,
                max_queries=self._max_queries,
                window_hours=self._window_hours,
                is_exceeded=current_count > self._max_queries,
            )

        except (OSError, orjson.JSONDecodeError, KeyError, ValueError) as e:  # type: ignore[attr-defined]
            logger.warning("Failed to read rate limit data: %s", e)  # type: ignore[arg-type]
            return RateLimitStatus(
                current_count=0,
                max_queries=self._max_queries,
                window_hours=self._window_hours,
                is_exceeded=False,
            )

    def get_uid_status(self, uid: str) -> PerUidRateLimitStatus:
        """Get rate limit status for a specific UID.

        Counts how many times this specific UID has been queried within the
        sliding window. Useful for checking BMF per-UID limits (2 per day).

        Args:
            uid: The VAT ID to check.

        Returns:
            Per-UID rate limit status with query count for this UID.
        """
        normalized_uid = uid.upper().strip()

        if not self.is_enabled or self._per_uid_limit <= 0:
            return PerUidRateLimitStatus(
                uid=normalized_uid,
                uid_count=0,
                per_uid_limit=self._per_uid_limit,
                is_uid_exceeded=False,
            )

        try:
            data = self._read_data()
            entries = _extract_entries_list(data)
            window_start = datetime.now(timezone.utc) - timedelta(hours=self._window_hours)

            # Count queries for this specific UID within the window
            uid_count = sum(1 for e in entries if _is_entry_within_window(e, window_start) and e.uid == normalized_uid)

            return PerUidRateLimitStatus(
                uid=normalized_uid,
                uid_count=uid_count,
                per_uid_limit=self._per_uid_limit,
                is_uid_exceeded=uid_count >= self._per_uid_limit,
            )

        except (OSError, orjson.JSONDecodeError, KeyError, ValueError) as e:  # type: ignore[attr-defined]
            logger.warning("Failed to read rate limit data for UID %s: %s", normalized_uid, e)  # type: ignore[arg-type]
            return PerUidRateLimitStatus(
                uid=normalized_uid,
                uid_count=0,
                per_uid_limit=self._per_uid_limit,
                is_uid_exceeded=False,
            )

    def record_call(self, uid: str) -> RateLimitStatus:
        """Record an API call and return updated status.

        This method should be called AFTER a successful or non-retryable
        API response. Retryable errors (service unavailable, rate limit
        exceeded, etc.) should NOT be recorded to avoid exhausting the
        local rate limit counter with failed attempts.

        Args:
            uid: The UID being queried (for logging/tracking purposes).

        Returns:
            Updated rate limit status after recording the call.
        """
        if not self.is_enabled:
            return RateLimitStatus(
                current_count=0,
                max_queries=self._max_queries,
                window_hours=self._window_hours,
                is_exceeded=False,
            )

        normalized_uid = uid.upper().strip()
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=self._window_hours)

        entry = RateLimitEntry(timestamp=now, uid=normalized_uid)

        try:
            current_count = self._write_entry(entry, window_start)
            is_exceeded = current_count > self._max_queries

            if is_exceeded:
                logger.warning(
                    "Rate limit exceeded: %d/%d queries in %.1fh window for UID %s",
                    current_count,
                    self._max_queries,
                    self._window_hours,
                    normalized_uid,
                )
            else:
                logger.debug(
                    "Rate limit status: %d/%d queries in %.1fh window",
                    current_count,
                    self._max_queries,
                    self._window_hours,
                )

            return RateLimitStatus(
                current_count=current_count,
                max_queries=self._max_queries,
                window_hours=self._window_hours,
                is_exceeded=is_exceeded,
            )

        except (OSError, Timeout) as e:
            logger.warning("Failed to record rate limit call: %s", e)
            return RateLimitStatus(
                current_count=0,
                max_queries=self._max_queries,
                window_hours=self._window_hours,
                is_exceeded=False,
            )

    def _ensure_dir(self) -> None:
        """Create rate limit file directory if it doesn't exist."""
        self._ratelimit_file.parent.mkdir(parents=True, exist_ok=True)

    def _read_data(self) -> dict[str, Any]:
        """Read and parse rate limit file with locking."""
        if not self._ratelimit_file.exists():
            return _empty_data()

        lock = FileLock(self._lock_file, timeout=_LOCK_TIMEOUT_SECONDS)
        with lock:
            content = self._ratelimit_file.read_bytes()
            return _parse_file_content(content)

    def _read_locked_data(self) -> dict[str, Any]:
        """Read data from file within an already-acquired lock."""
        if not self._ratelimit_file.exists():
            return _empty_data()
        content = self._ratelimit_file.read_bytes()
        return _parse_file_content(content)

    def _cleanup_and_append(self, data: dict[str, Any], entry: RateLimitEntry, window_start: datetime) -> list[RateLimitEntry]:
        """Cleanup old entries, enforce size limit, and append new entry."""
        entries = _extract_entries_list(data)

        # First, remove entries outside the sliding window
        entries, window_removed = _cleanup_old_entries(entries, window_start)
        if window_removed > 0:
            logger.debug("Cleaned up %d old rate limit entries", window_removed)

        # Add new entry
        entries.append(entry)

        # Trim oldest entries if over limit
        entries, trimmed = _trim_oldest_ratelimit_entries(entries, self._max_entries)
        if trimmed > 0:
            logger.debug("Trimmed %d oldest rate limit entries (max_entries=%d)", trimmed, self._max_entries)

        return entries

    def _write_entry(self, entry: RateLimitEntry, window_start: datetime) -> int:
        """Write entry to rate limit file with locking and cleanup.

        Args:
            entry: The API call entry to record.
            window_start: Start of the sliding window for cleanup.

        Returns:
            Current count of entries in the window after adding new entry.
        """
        self._ensure_dir()

        lock = FileLock(self._lock_file, timeout=_LOCK_TIMEOUT_SECONDS)
        with lock:
            data = self._read_locked_data()
            entries = self._cleanup_and_append(data, entry, window_start)
            # Serialize entries to dicts for JSON storage
            data["api_calls"] = [e.to_dict() for e in entries]

            # Update metadata
            data["metadata"]["last_cleanup"] = format_iso_datetime(datetime.now(timezone.utc))

            # Write back
            self._ratelimit_file.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_UTC_Z))

            return len(entries)

    def clear(self) -> None:
        """Remove all rate limit records."""
        lock = FileLock(self._lock_file, timeout=_LOCK_TIMEOUT_SECONDS)
        try:
            with lock:
                if self._ratelimit_file.exists():
                    self._ratelimit_file.unlink()
                    logger.info("Rate limit data cleared")
        except (OSError, Timeout) as e:
            logger.warning("Failed to clear rate limit data: %s", e)
