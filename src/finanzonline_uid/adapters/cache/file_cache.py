"""File-based cache for UID verification results.

Provides persistent caching of successful UID query results with file locking
for safe concurrent access on network drives.

Contents:
    * :class:`UidResultCache` - Thread-safe file cache with expiration
    * :class:`CacheEntry` - One cached result, validated from and dumped to the cache file
    * :class:`AddressRecord` - The six address lines as stored in the cache file

System Role:
    Acts as a caching adapter that stores successful UID verification results
    to disk, reducing redundant API calls to FinanzOnline while ensuring
    data integrity through file locking.

    The cache file is a JSON object mapping each normalized UID to one entry.
    Installed versions of this tool read and rewrite the same file, so the
    entry shape (keys, key order, timestamp form) is a fixed wire format.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import orjson
from filelock import FileLock, Timeout
from pydantic import BaseModel, ConfigDict, ValidationError

from finanzonline_uid._datetime_utils import WireDatetime, format_iso_datetime
from finanzonline_uid.domain.models import Address, UidCheckResult

__all__ = ["AddressRecord", "CacheEntry", "UidResultCache"]

logger = logging.getLogger(__name__)

_LOCK_TIMEOUT_SECONDS = 10.0
_DEFAULT_MAX_CACHE_ENTRIES = 1000


class AddressRecord(BaseModel):
    """Company address as stored in the cache file.

    A separate record (rather than dumping the domain Address) keeps the
    on-disk shape fixed even if the domain type gains fields. Every line
    defaults to "" because installed versions read missing lines that way.

    Attributes:
        line1: First address line.
        line2: Second address line.
        line3: Third address line.
        line4: Fourth address line.
        line5: Fifth address line.
        line6: Sixth address line.

    Examples:
        >>> AddressRecord.model_validate({"line3": "1010 Wien"}).to_address()
        Address(line1='', line2='', line3='1010 Wien', line4='', line5='', line6='')
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    line1: str = ""
    line2: str = ""
    line3: str = ""
    line4: str = ""
    line5: str = ""
    line6: str = ""

    @classmethod
    def from_address(cls, address: Address) -> AddressRecord:
        """Build the stored form of a domain address.

        Args:
            address: Domain address.

        Returns:
            AddressRecord with the same six lines.
        """
        return cls(
            line1=address.line1,
            line2=address.line2,
            line3=address.line3,
            line4=address.line4,
            line5=address.line5,
            line6=address.line6,
        )

    def to_address(self) -> Address:
        """Convert to the domain address.

        Returns:
            Address with the same six lines.
        """
        return Address(
            line1=self.line1,
            line2=self.line2,
            line3=self.line3,
            line4=self.line4,
            line5=self.line5,
            line6=self.line6,
        )


class CacheEntry(BaseModel):
    """Single cache entry with expiration metadata.

    Field order is the on-disk key order. message, name and address are
    optional because installed versions read their absence as "", "" and
    None.

    Attributes:
        uid: The cached UID.
        return_code: FinanzOnline return code.
        message: Status message.
        name: Company name.
        address: Company address or None.
        queried_at: Original query timestamp (UTC).
        expires_at: Expiration timestamp (UTC).
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    uid: str
    return_code: int
    message: str = ""
    name: str = ""
    address: AddressRecord | None = None
    queried_at: WireDatetime
    expires_at: WireDatetime

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
            address=self.address.to_address() if self.address is not None else None,
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
            address=AddressRecord.from_address(result.address) if result.address is not None else None,
            queried_at=result.timestamp,
            expires_at=expires_at,
        )


def _parse_entries(content: bytes) -> dict[str, CacheEntry]:
    """Validate the cache file content entry by entry.

    A top-level value that is not an object reads as an empty cache, and an
    entry that fails validation is skipped, as installed versions do. Invalid
    JSON raises so that a write never overwrites a file it could not read.

    Args:
        content: Raw cache file bytes.

    Returns:
        Valid entries keyed by UID, in file order.

    Raises:
        orjson.JSONDecodeError: The content is not valid JSON.

    Examples:
        >>> _parse_entries(b"")
        {}
        >>> _parse_entries(b"[1, 2]")
        {}
        >>> _parse_entries(b'{"X": {"uid": "X"}}')
        {}
    """
    if not content:
        return {}
    loaded: object = orjson.loads(content)
    if not isinstance(loaded, dict):
        return {}
    entries: dict[str, CacheEntry] = {}
    # JSON object keys are always strings, so only the values need validating.
    for uid, raw_entry in cast(dict[str, object], loaded).items():
        try:
            entries[uid] = CacheEntry.model_validate(raw_entry)
        except ValidationError:
            logger.debug("Skipping malformed cache entry for UID %s", uid)
    return entries


def _serialize_entries(entries: dict[str, CacheEntry]) -> bytes:
    """Dump entries with the serializer call installed versions use.

    Args:
        entries: Entries keyed by UID, in the order to write them.

    Returns:
        File content bytes.
    """
    wire = {uid: entry.model_dump(mode="json") for uid, entry in entries.items()}
    return orjson.dumps(wire, option=orjson.OPT_INDENT_2 | orjson.OPT_UTC_Z)


def _drop_expired(entries: dict[str, CacheEntry]) -> dict[str, CacheEntry]:
    """Return the unexpired entries, keeping their order."""
    return {uid: entry for uid, entry in entries.items() if not entry.is_expired()}


def _trim_oldest_entries(entries: dict[str, CacheEntry], max_entries: int) -> dict[str, CacheEntry]:
    """Keep only the newest max_entries entries by query time.

    Below the limit the map is returned unchanged, so file order is kept;
    above it the result is ordered oldest first, as installed versions write it.

    Args:
        entries: Entries keyed by UID.
        max_entries: Maximum number of entries to keep.

    Returns:
        The kept entries.
    """
    if len(entries) <= max_entries:
        return entries
    by_age = sorted(entries.items(), key=lambda item: item[1].queried_at)
    return dict(by_age[len(entries) - max_entries :])


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
            entry = self._read_cache().get(normalized_uid)
        except (OSError, orjson.JSONDecodeError) as e:
            logger.warning("Failed to read cache: %s", e)
            return None

        if entry is None:
            logger.debug("Cache miss for UID %s", normalized_uid)
            return None

        if entry.is_expired():
            logger.debug("Cache entry expired for UID %s", normalized_uid)
            return None

        logger.info("Cache hit for UID %s (cached at %s)", normalized_uid, format_iso_datetime(entry.queried_at))
        return entry.to_result()

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
            self._write_entry(normalized_uid, entry)
            logger.info("Cached result for UID %s (expires %s)", normalized_uid, format_iso_datetime(entry.expires_at))
        except (OSError, Timeout) as e:
            logger.warning("Failed to write cache: %s", e)

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist."""
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)

    def _read_cache(self) -> dict[str, CacheEntry]:
        """Read and validate the cache file with locking."""
        if not self._cache_file.exists():
            return {}

        lock = FileLock(self._lock_file, timeout=_LOCK_TIMEOUT_SECONDS)
        with lock:
            return _parse_entries(self._cache_file.read_bytes())

    def _read_locked_entries(self) -> dict[str, CacheEntry]:
        """Read and validate the cache file within an already-acquired lock."""
        if not self._cache_file.exists():
            return {}
        return _parse_entries(self._cache_file.read_bytes())

    def _write_entry(self, uid: str, entry: CacheEntry) -> None:
        """Write entry to cache with locking, cleanup, and size limit enforcement."""
        self._ensure_cache_dir()

        lock = FileLock(self._lock_file, timeout=_LOCK_TIMEOUT_SECONDS)
        with lock:
            stored = self._read_locked_entries()

            entries = _drop_expired(stored)
            expired_removed = len(stored) - len(entries)
            if expired_removed > 0:
                logger.debug("Cleaned up %d expired cache entries", expired_removed)

            # Assigning to an existing UID keeps its position in the file,
            # matching what installed versions write.
            entries[uid] = entry

            kept = _trim_oldest_entries(entries, self._max_entries)
            trimmed = len(entries) - len(kept)
            if trimmed > 0:
                logger.debug("Trimmed %d oldest cache entries (max_entries=%d)", trimmed, self._max_entries)

            self._cache_file.write_bytes(_serialize_entries(kept))

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
