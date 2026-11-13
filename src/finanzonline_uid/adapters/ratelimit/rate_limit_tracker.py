"""File-based rate limit tracker for UID verification queries.

Provides tracking of API call frequency with file locking for safe
concurrent access on network drives. Uses sliding window algorithm.

Contents:
    * :class:`RateLimitStatus` - Current rate limit status
    * :class:`PerUidRateLimitStatus` - Per-UID rate limit status
    * :class:`RateLimitTracker` - Thread-safe rate limit tracker
    * :class:`RateLimitEntry` / :class:`RateLimitMetadata` / :class:`RateLimitFile` -
      the rate-limit file, validated on read and dumped on write

System Role:
    Acts as a rate limiting adapter that tracks API calls to FinanzOnline,
    warning users when configured limits are exceeded while ensuring
    data integrity through file locking.

    Installed versions of this tool read and rewrite the same file, so its
    shape (keys, key order, timestamp form) is a fixed wire format.
    A file that is not valid JSON counts no calls; a write keeps its bytes
    aside (see :func:`set_aside_unreadable`) and starts the file afresh.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import orjson
from filelock import FileLock, Timeout
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from finanzonline_uid._datetime_utils import WireDatetime
from finanzonline_uid.adapters._state_file import set_aside_unreadable

__all__ = [
    "PerUidRateLimitStatus",
    "RateLimitEntry",
    "RateLimitFile",
    "RateLimitMetadata",
    "RateLimitStatus",
    "RateLimitTracker",
]

logger = logging.getLogger(__name__)

_LOCK_TIMEOUT_SECONDS = 10.0
_DEFAULT_MAX_RATELIMIT_ENTRIES = 10000
_DEFAULT_PER_UID_LIMIT = 2  # BMF service limit: 2 queries per UID per day


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


class RateLimitEntry(BaseModel):
    """A single rate limit tracking entry.

    Field order is the on-disk key order. uid defaults to "" because
    installed versions read a missing uid that way.

    Attributes:
        timestamp: When the API call was made (UTC).
        uid: The UID that was queried.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    timestamp: WireDatetime
    uid: str = ""


class RateLimitMetadata(BaseModel):
    """Bookkeeping stored next to the call list.

    Attributes:
        last_cleanup: When the file was last rewritten, None before the first write.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    last_cleanup: WireDatetime | None = None


def _valid_entry(raw: object) -> RateLimitEntry | None:
    """Validate one stored call, None when it is malformed."""
    try:
        return RateLimitEntry.model_validate(raw)
    except ValidationError:
        return None


class RateLimitFile(BaseModel):
    """The whole rate-limit file.

    Validation is tolerant where installed versions were: a call list that
    is not a list reads as empty, a malformed call is skipped, and unusable
    metadata is replaced by a fresh one (every write replaces it anyway).

    Attributes:
        api_calls: Recorded calls in file order.
        metadata: File bookkeeping.

    Examples:
        >>> RateLimitFile.model_validate({"api_calls": "x"}).api_calls
        ()
        >>> calls = [{"uid": "A"}, {"timestamp": "2025-01-01T00:00:00Z"}]
        >>> len(RateLimitFile.model_validate({"api_calls": calls}).api_calls)
        1
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    api_calls: tuple[RateLimitEntry, ...] = ()
    metadata: RateLimitMetadata = RateLimitMetadata()

    @field_validator("api_calls", mode="before")
    @classmethod
    def _skip_malformed_calls(cls, value: object) -> tuple[RateLimitEntry, ...]:
        """Keep only the calls that validate; a non-list holds no calls."""
        if not isinstance(value, (list, tuple)):
            return ()
        candidates = (_valid_entry(raw) for raw in cast("list[object]", value))
        return tuple(entry for entry in candidates if entry is not None)

    @field_validator("metadata", mode="before")
    @classmethod
    def _reset_unusable_metadata(cls, value: object) -> RateLimitMetadata:
        """Read metadata that does not validate as fresh metadata."""
        try:
            return RateLimitMetadata.model_validate(value)
        except ValidationError:
            return RateLimitMetadata()


def _parse_file_content(content: bytes) -> RateLimitFile:
    """Validate the rate-limit file content.

    Empty content and a top-level value that is not an object read as an
    empty file, as installed versions do. Invalid JSON raises, so a reader can
    report it and a writer can keep the bytes aside instead of overwriting them.

    Args:
        content: Raw file bytes.

    Returns:
        The validated file.

    Raises:
        orjson.JSONDecodeError: The content is not valid JSON.

    Examples:
        >>> _parse_file_content(b"[1]").api_calls
        ()
    """
    if not content:
        return RateLimitFile()
    loaded: object = orjson.loads(content)
    if not isinstance(loaded, dict):
        return RateLimitFile()
    return RateLimitFile.model_validate(loaded)


def _serialize_file(data: RateLimitFile) -> bytes:
    """Dump the file with the serializer call installed versions use."""
    return orjson.dumps(data.model_dump(mode="json"), option=orjson.OPT_INDENT_2 | orjson.OPT_UTC_Z)


def _is_entry_within_window(entry: RateLimitEntry, window_start: datetime) -> bool:
    """Check if an entry's timestamp is within the sliding window."""
    return entry.timestamp >= window_start


def _entries_within_window(entries: tuple[RateLimitEntry, ...], window_start: datetime) -> list[RateLimitEntry]:
    """Return the entries inside the sliding window, keeping their order."""
    return [e for e in entries if _is_entry_within_window(e, window_start)]


def _trim_oldest_ratelimit_entries(entries: list[RateLimitEntry], max_entries: int) -> list[RateLimitEntry]:
    """Keep only the newest max_entries entries.

    Below the limit the list is returned unchanged, so file order is kept;
    above it the result is ordered oldest first, as installed versions write it.

    Args:
        entries: Recorded calls.
        max_entries: Maximum number of entries to keep.

    Returns:
        The kept entries.
    """
    if len(entries) <= max_entries:
        return entries
    by_age = sorted(entries, key=lambda e: e.timestamp)
    return by_age[len(entries) - max_entries :]


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

    def _idle_status(self) -> RateLimitStatus:
        """Status reported when nothing is counted (disabled or unreadable)."""
        return RateLimitStatus(
            current_count=0,
            max_queries=self._max_queries,
            window_hours=self._window_hours,
            is_exceeded=False,
        )

    def get_status(self) -> RateLimitStatus:
        """Get current rate limit status without recording a call.

        Returns:
            Current rate limit status with count of queries in window.
        """
        if not self.is_enabled:
            return self._idle_status()

        try:
            data = self._read_data()
        except (OSError, orjson.JSONDecodeError) as e:
            logger.warning("Failed to read rate limit data: %s", e)
            return self._idle_status()

        window_start = datetime.now(timezone.utc) - timedelta(hours=self._window_hours)
        current_count = len(_entries_within_window(data.api_calls, window_start))
        return RateLimitStatus(
            current_count=current_count,
            max_queries=self._max_queries,
            window_hours=self._window_hours,
            is_exceeded=current_count > self._max_queries,
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
        idle = PerUidRateLimitStatus(
            uid=normalized_uid,
            uid_count=0,
            per_uid_limit=self._per_uid_limit,
            is_uid_exceeded=False,
        )

        if not self.is_enabled or self._per_uid_limit <= 0:
            return idle

        try:
            data = self._read_data()
        except (OSError, orjson.JSONDecodeError) as e:
            logger.warning("Failed to read rate limit data for UID %s: %s", normalized_uid, e)
            return idle

        window_start = datetime.now(timezone.utc) - timedelta(hours=self._window_hours)
        uid_count = sum(1 for e in _entries_within_window(data.api_calls, window_start) if e.uid == normalized_uid)
        return PerUidRateLimitStatus(
            uid=normalized_uid,
            uid_count=uid_count,
            per_uid_limit=self._per_uid_limit,
            is_uid_exceeded=uid_count >= self._per_uid_limit,
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
            return self._idle_status()

        normalized_uid = uid.upper().strip()
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=self._window_hours)

        entry = RateLimitEntry(timestamp=now, uid=normalized_uid)

        try:
            current_count = self._write_entry(entry, window_start)
        except (OSError, Timeout) as e:
            logger.warning("Failed to record rate limit call: %s", e)
            return self._idle_status()

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

    def _ensure_dir(self) -> None:
        """Create rate limit file directory if it doesn't exist."""
        self._ratelimit_file.parent.mkdir(parents=True, exist_ok=True)

    def _read_data(self) -> RateLimitFile:
        """Read and validate the rate limit file with locking."""
        if not self._ratelimit_file.exists():
            return RateLimitFile()

        lock = FileLock(self._lock_file, timeout=_LOCK_TIMEOUT_SECONDS)
        with lock:
            return _parse_file_content(self._ratelimit_file.read_bytes())

    def _read_locked_data(self) -> RateLimitFile:
        """Read the rate limit file for a rewrite, within an already-acquired lock.

        An unparsable file is moved aside and reads as empty: the call being
        recorded already reached FinanzOnline, so refusing the write would turn
        a successful check into a failure, and overwriting would lose the bytes.
        """
        if not self._ratelimit_file.exists():
            return RateLimitFile()
        try:
            return _parse_file_content(self._ratelimit_file.read_bytes())
        except orjson.JSONDecodeError:
            set_aside_unreadable(self._ratelimit_file, now=datetime.now(timezone.utc))
            return RateLimitFile()

    def _cleanup_and_append(
        self,
        stored: tuple[RateLimitEntry, ...],
        entry: RateLimitEntry,
        window_start: datetime,
    ) -> list[RateLimitEntry]:
        """Drop entries outside the window, append the new entry, enforce the size limit."""
        entries = _entries_within_window(stored, window_start)
        window_removed = len(stored) - len(entries)
        if window_removed > 0:
            logger.debug("Cleaned up %d old rate limit entries", window_removed)

        entries.append(entry)

        kept = _trim_oldest_ratelimit_entries(entries, self._max_entries)
        trimmed = len(entries) - len(kept)
        if trimmed > 0:
            logger.debug("Trimmed %d oldest rate limit entries (max_entries=%d)", trimmed, self._max_entries)

        return kept

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
            stored = self._read_locked_data()
            entries = self._cleanup_and_append(stored.api_calls, entry, window_start)
            updated = RateLimitFile(
                api_calls=tuple(entries),
                metadata=RateLimitMetadata(last_cleanup=datetime.now(timezone.utc)),
            )
            self._ratelimit_file.write_bytes(_serialize_file(updated))
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
