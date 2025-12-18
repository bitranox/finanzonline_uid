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

from uid_check_austria._datetime_utils import format_iso_datetime, parse_iso_datetime
from uid_check_austria.domain.models import Address, UidCheckResult

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
        address: Company address dict or None.
        queried_at: Original query timestamp (ISO format string).
        expires_at: Expiration timestamp (ISO format string).
    """

    uid: str
    return_code: int
    message: str
    name: str
    address: dict[str, str] | None
    queried_at: str
    expires_at: str


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


def _result_to_cache_entry(result: UidCheckResult, expires_at: datetime) -> dict[str, Any]:
    """Convert UidCheckResult to cache entry dict."""
    return {
        "uid": result.uid,
        "return_code": result.return_code,
        "message": result.message,
        "name": result.name,
        "address": _address_to_dict(result.address),
        "queried_at": format_iso_datetime(result.timestamp),
        "expires_at": format_iso_datetime(expires_at),
    }


def _cache_entry_to_result(entry: dict[str, Any]) -> UidCheckResult:
    """Convert cache entry dict to UidCheckResult with cache flags set."""
    queried_at = parse_iso_datetime(entry["queried_at"])
    return UidCheckResult(
        uid=entry["uid"],
        return_code=entry["return_code"],
        message=entry["message"],
        name=entry.get("name", ""),
        address=_dict_to_address(entry.get("address")),
        timestamp=datetime.now(timezone.utc),
        from_cache=True,
        cached_at=queried_at,
    )


def _is_entry_expired(entry: dict[str, Any]) -> bool:
    """Check if cache entry has expired."""
    expires_at = parse_iso_datetime(entry["expires_at"])
    return datetime.now(timezone.utc) >= expires_at


def _cleanup_expired_entries(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Remove expired entries from cache data.

    Returns:
        Tuple of (cleaned data, number of entries removed).
    """
    original_count = len(data)
    cleaned = {uid: entry for uid, entry in data.items() if not _is_entry_expired(entry)}
    removed_count = original_count - len(cleaned)
    return cleaned, removed_count


class UidResultCache:
    """File-based cache for UID verification results.

    Stores successful UID query results in a JSON file with file locking
    for safe concurrent access. Automatically cleans up expired entries.

    Attributes:
        cache_file: Path to the cache JSON file.
        cache_hours: Number of hours to cache results.

    Example:
        >>> cache = UidResultCache(Path("/tmp/uid_cache.json"), cache_hours=24.0)
        >>> result = cache.get("ATU12345678")
        >>> if result is None:
        ...     # Query not cached, perform actual lookup
        ...     pass
    """

    def __init__(self, cache_file: Path, cache_hours: float) -> None:
        """Initialize cache with file path and expiration time.

        Args:
            cache_file: Path to the JSON cache file.
            cache_hours: Hours until cached entries expire.
        """
        self._cache_file = cache_file
        self._cache_hours = cache_hours
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
            entry = data.get(normalized_uid)

            if entry is None:
                logger.debug("Cache miss for UID %s", normalized_uid)
                return None

            if _is_entry_expired(entry):
                logger.debug("Cache entry expired for UID %s", normalized_uid)
                return None

            result = _cache_entry_to_result(entry)
            logger.info("Cache hit for UID %s (cached at %s)", normalized_uid, entry["queried_at"])
            return result

        except (OSError, orjson.JSONDecodeError, KeyError, ValueError) as e:  # type: ignore[attr-defined]
            logger.warning("Failed to read cache: %s", e)  # type: ignore[arg-type]
            return None

    def put(self, result: UidCheckResult) -> None:
        """Store a successful result in the cache.

        Only caches results with return_code == 0 (valid UIDs).

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
        entry = _result_to_cache_entry(result, expires_at)

        try:
            self._write_entry(normalized_uid, entry)
            logger.info("Cached result for UID %s (expires %s)", normalized_uid, entry["expires_at"])
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
        """Write entry to cache with locking and cleanup."""
        self._ensure_cache_dir()

        lock = FileLock(self._lock_file, timeout=_LOCK_TIMEOUT_SECONDS)
        with lock:
            data = self._read_locked_data()
            data, removed = _cleanup_expired_entries(data)
            if removed > 0:
                logger.debug("Cleaned up %d expired cache entries", removed)
            data[uid] = entry
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
