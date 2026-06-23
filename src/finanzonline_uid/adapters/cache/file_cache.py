"""File-based cache for UID verification results.

Provides persistent caching of successful UID query results with file locking
for safe concurrent access on network drives.

Contents:
    * :class:`UidResultCache` - Thread-safe file cache with expiration

System Role:
    Acts as a caching adapter that stores successful UID verification results
    to disk, reducing redundant API calls to FinanzOnline while ensuring
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
from finanzonline_uid.domain.models import Address, UidCheckResult

logger = logging.getLogger(__name__)

_LOCK_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """Single cache entry with expiration metadata.

    Attributes:
        uid: The cached UID.
        return_code: FinanzOnline return code.
        message: Status message.
        name: Company name.
        address: Company address or None.
        queried_at: Original query timestamp (UTC).
        expires_at: Expiration timestamp (UTC).
    """

    uid: str
    return_code: int
    message: str
    name: str
    address: Address | None
    queried_at: datetime
    expires_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize entry to dictionary for JSON storage."""
        return {
            "uid": self.uid,
            "return_code": self.return_code,
            "message": self.message,
            "name": self.name,
            "address": _address_to_dict(self.address),
            "queried_at": format_iso_datetime(self.queried_at),
            "expires_at": format_iso_datetime(self.expires_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheEntry:
        """Deserialize entry from dictionary.

        Args:
            data: Dictionary with cache entry fields.

        Returns:
            CacheEntry instance.
        """
        return cls(
            uid=str(data["uid"]),
            return_code=int(data["return_code"]),
            message=str(data.get("message", "")),
            name=str(data.get("name", "")),
            address=_dict_to_address(data.get("address")),
            queried_at=parse_iso_datetime(data["queried_at"]),
            expires_at=parse_iso_datetime(data["expires_at"]),
        )

    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        return datetime.now(timezone.utc) >= self.expires_at

    def to_result(self) -> UidCheckResult:
        """Convert this cache entry to a UidCheckResult with cache flags set."""
        return UidCheckResult(
            uid=self.uid,
            return_code=self.return_code,
            message=self.message,
            name=self.name,
            address=self.address,
            timestamp=self.queried_at,
            from_cache=True,
            cached_at=self.queried_at,
        )

    @classmethod
    def from_result(cls, result: UidCheckResult, expires_at: datetime) -> CacheEntry:
        """Create a cache entry from a UidCheckResult.

        Args:
            result: The result to cache.
            expires_at: When this entry should expire.

        Returns:
            CacheEntry instance.
        """
        return cls(
            uid=result.uid,
            return_code=result.return_code,
            message=result.message,
            name=result.name,
            address=result.address,
            queried_at=result.timestamp,
            expires_at=expires_at,
        )


def _address_to_dict(address: Address | None) -> dict[str, str] | None:
    """Convert Address to dict for JSON serialization."""
    if address is None:
        return None
    return {
        "line1": address.line1,
        "line2": address.line2,
        "line3": address.line3,
        "line4": address.line4,
        "line5": address.line5,
        "line6": address.line6,
    }


def _dict_to_address(data: dict[str, str] | None) -> Address | None:
    """Convert dict back to Address object."""
    if data is None:
        return None
    return Address(
        line1=data.get("line1", ""),
        line2=data.get("line2", ""),
        line3=data.get("line3", ""),
        line4=data.get("line4", ""),
        line5=data.get("line5", ""),
        line6=data.get("line6", ""),
    )


def _cleanup_expired_entries(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Remove expired entries from cache data.

    Returns:
        Tuple of (cleaned data, number of entries removed).
    """
    original_count = len(data)
    cleaned: dict[str, Any] = {}
    for uid, entry_dict in data.items():
        try:
            entry = CacheEntry.from_dict(entry_dict)
            if not entry.is_expired():
                cleaned[uid] = entry_dict
        except (KeyError, ValueError):
            continue  # Skip malformed entries
    removed_count = original_count - len(cleaned)
    return cleaned, removed_count


_DEFAULT_MAX_CACHE_ENTRIES = 1000


def _trim_oldest_entries(data: dict[str, Any], max_entries: int) -> tuple[dict[str, Any], int]:
    """Trim oldest entries to stay within max_entries limit.

    Sorts entries by queried_at timestamp and keeps only the newest max_entries.

    Returns:
        Tuple of (trimmed data, number of entries removed).
    """
    if len(data) <= max_entries:
        return data, 0

    # Sort by queried_at (oldest first) and keep newest entries
    sorted_items = sorted(
        data.items(),
        key=lambda item: item[1].get("queried_at", ""),
    )
    entries_to_remove = len(data) - max_entries
    trimmed = dict(sorted_items[entries_to_remove:])
    return trimmed, entries_to_remove


class UidResultCache:
    """File-based cache for UID verification results.

    Stores successful UID query results in a JSON file with file locking
    for safe concurrent access. Automatically cleans up expired entries
    and enforces a maximum entry limit to prevent unbounded growth.

    Attributes:
        cache_file: Path to the cache JSON file.
        cache_hours: Number of hours to cache results.
        max_entries: Maximum number of entries to keep in cache.

    Example:
        >>> cache = UidResultCache(Path("/tmp/uid_cache.json"), cache_hours=24.0)
        >>> result = cache.get("ATU12345678")
        >>> if result is None:
        ...     # Query not cached, perform actual lookup
        ...     pass
    """

    def __init__(
        self,
        cache_file: Path,
        cache_hours: float,
        max_entries: int = _DEFAULT_MAX_CACHE_ENTRIES,
    ) -> None:
        """Initialize cache with file path and expiration time.

        Args:
            cache_file: Path to the JSON cache file.
            cache_hours: Hours until cached entries expire.
            max_entries: Maximum entries to keep (default 1000). Oldest
                entries are removed when limit is exceeded.
        """
        self._cache_file = cache_file
        self._cache_hours = cache_hours
        self._max_entries = max_entries
        self._lock_file = cache_file.with_suffix(".lock")

    @property
    def cache_file(self) -> Path:
        """Return the cache file path."""
        return self._cache_file

    @property
    def cache_hours(self) -> float:
        """Return the cache duration in hours."""
        return self._cache_hours

    @property
    def is_enabled(self) -> bool:
        """Check if caching is enabled (cache_hours > 0)."""
        return self._cache_hours > 0

    @property
    def max_entries(self) -> int:
        """Return the maximum number of cache entries."""
        return self._max_entries

    def get(self, uid: str) -> UidCheckResult | None:
        """Get cached result for UID if valid and not expired.

        Args:
            uid: The VAT ID to look up.

        Returns:
            Cached UidCheckResult with from_cache=True if found and valid,
            None if not cached or expired.
        """
        if not self.is_enabled:
            return None

        normalized_uid = uid.upper().strip()

        try:
            data = self._read_cache()
            entry_dict = data.get(normalized_uid)

            if entry_dict is None:
                logger.debug("Cache miss for UID %s", normalized_uid)
                return None

            entry = CacheEntry.from_dict(entry_dict)

            if entry.is_expired():
                logger.debug("Cache entry expired for UID %s", normalized_uid)
                return None

            result = entry.to_result()
            logger.info("Cache hit for UID %s (cached at %s)", normalized_uid, format_iso_datetime(entry.queried_at))
            return result

        except (OSError, orjson.JSONDecodeError, KeyError, ValueError) as e:  # type: ignore[attr-defined]
            logger.warning("Failed to read cache: %s", e)  # type: ignore[arg-type]
            return None

    def put(self, result: UidCheckResult) -> None:
        """Store a successful result in the cache.

        Only caches results with return_code == ReturnCode.UID_VALID (valid UIDs).

        Args:
            result: The UidCheckResult to cache.
        """
        if not self.is_enabled:
            return

        if not result.is_valid:
            logger.debug("Not caching invalid result for UID %s", result.uid)
            return

        normalized_uid = result.uid.upper().strip()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self._cache_hours)
        entry = CacheEntry.from_result(result, expires_at)

        try:
            self._write_entry(normalized_uid, entry.to_dict())
            logger.info("Cached result for UID %s (expires %s)", normalized_uid, format_iso_datetime(entry.expires_at))
        except (OSError, Timeout) as e:
            logger.warning("Failed to write cache: %s", e)

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist."""
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)

    def _parse_file_content(self, content: bytes) -> dict[str, Any]:
        """Parse file content into a dict, returning empty dict on failure."""
        if not content:
            return {}
        loaded = orjson.loads(content)
        return cast(dict[str, Any], loaded) if isinstance(loaded, dict) else {}

    def _read_cache(self) -> dict[str, Any]:
        """Read and parse cache file with locking."""
        if not self._cache_file.exists():
            return {}

        lock = FileLock(self._lock_file, timeout=_LOCK_TIMEOUT_SECONDS)
        with lock:
            content = self._cache_file.read_bytes()
            return self._parse_file_content(content)

    def _read_locked_data(self) -> dict[str, Any]:
        """Read cache data within an already-acquired lock."""
        if not self._cache_file.exists():
            return {}
        content = self._cache_file.read_bytes()
        return self._parse_file_content(content)

    def _write_entry(self, uid: str, entry: dict[str, Any]) -> None:
        """Write entry to cache with locking, cleanup, and size limit enforcement."""
        self._ensure_cache_dir()

        lock = FileLock(self._lock_file, timeout=_LOCK_TIMEOUT_SECONDS)
        with lock:
            data = self._read_locked_data()

            # First, remove expired entries
            data, expired_removed = _cleanup_expired_entries(data)
            if expired_removed > 0:
                logger.debug("Cleaned up %d expired cache entries", expired_removed)

            # Add new entry
            data[uid] = entry

            # Trim oldest entries if over limit
            data, trimmed = _trim_oldest_entries(data, self._max_entries)
            if trimmed > 0:
                logger.debug("Trimmed %d oldest cache entries (max_entries=%d)", trimmed, self._max_entries)

            self._cache_file.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_UTC_Z))

    def clear(self) -> None:
        """Remove all cached entries."""
        lock = FileLock(self._lock_file, timeout=_LOCK_TIMEOUT_SECONDS)
        try:
            with lock:
                if self._cache_file.exists():
                    self._cache_file.unlink()
                    logger.info("Cache cleared")
        except (OSError, Timeout) as e:
            logger.warning("Failed to clear cache: %s", e)
