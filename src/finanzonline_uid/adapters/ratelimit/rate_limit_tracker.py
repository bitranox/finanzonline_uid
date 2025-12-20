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


def _is_entry_within_window(entry: dict[str, Any], window_start: datetime) -> bool:
    """Check if an entry's timestamp is within the sliding window."""
    entry_time = parse_iso_datetime(entry["timestamp"])
    return entry_time >= window_start


def _cleanup_old_entries(entries: list[dict[str, Any]], window_start: datetime) -> tuple[list[dict[str, Any]], int]:
    """Remove entries older than the window start.

    Returns:
        Tuple of (cleaned entries, number of entries removed).
    """
    original_count = len(entries)
    cleaned = [e for e in entries if _is_entry_within_window(e, window_start)]
    removed_count = original_count - len(cleaned)
    return cleaned, removed_count


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


def _extract_entries_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract api_calls list from data, ensuring it's a list."""
    raw_entries = data.get("api_calls", [])
    if isinstance(raw_entries, list):
        return cast(list[dict[str, Any]], raw_entries)
    return []


class RateLimitTracker:
    """File-based rate limit tracker with sliding window.

    Tracks API calls to FinanzOnline in a JSON file with file locking
    for safe concurrent access. Uses a sliding window to count recent
    queries and determine if the rate limit is exceeded.

    Attributes:
        ratelimit_file: Path to the rate limit JSON file.
        max_queries: Maximum queries allowed within the window.
        window_hours: Duration of the sliding window in hours.

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

    def __init__(self, ratelimit_file: Path, max_queries: int, window_hours: float) -> None:
        """Initialize rate limit tracker.

        Args:
            ratelimit_file: Path to the JSON rate limit file.
            max_queries: Maximum queries allowed in the window.
            window_hours: Duration of the sliding window in hours.
        """
        self._ratelimit_file = ratelimit_file
        self._max_queries = max_queries
        self._window_hours = window_hours
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
            entries = data.get("api_calls", [])
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

    def record_call(self, uid: str) -> RateLimitStatus:
        """Record an API call and return updated status.

        This method should be called BEFORE making the actual API call
        to ensure the count is incremented even if the call fails.

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

        entry = {
            "timestamp": format_iso_datetime(now),
            "uid": normalized_uid,
        }

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

    def _cleanup_and_append(self, data: dict[str, Any], entry: dict[str, Any], window_start: datetime) -> list[dict[str, Any]]:
        """Cleanup old entries and append new entry."""
        entries = _extract_entries_list(data)
        entries, removed = _cleanup_old_entries(entries, window_start)
        if removed > 0:
            logger.debug("Cleaned up %d old rate limit entries", removed)
        entries.append(entry)
        return entries

    def _write_entry(self, entry: dict[str, Any], window_start: datetime) -> int:
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
            data["api_calls"] = entries

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
