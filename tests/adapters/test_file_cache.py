"""Tests for file-based UID result cache.

Tests cover:
- Basic get/put operations
- Cache expiration handling
- Cache cleanup of expired entries
- File locking behavior
- Error handling for corrupt/missing cache files
- Address serialization round-trip
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import orjson
import pytest

from finanzonline_uid.adapters.cache import UidResultCache
from finanzonline_uid.domain.models import Address, UidCheckResult


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def cache_file(tmp_path: Path) -> Path:
    """Provide a temporary cache file path."""
    return tmp_path / "test_cache.json"


@pytest.fixture
def cache(cache_file: Path) -> UidResultCache:
    """Provide a cache instance with 24-hour expiry."""
    return UidResultCache(cache_file=cache_file, cache_hours=24.0)


@pytest.fixture
def valid_result() -> UidCheckResult:
    """Provide a valid UID result for caching."""
    return UidCheckResult(
        uid="ATU12345678",
        return_code=0,
        message="UID is valid",
        name="Test Company GmbH",
        address=Address(
            line1="Test Company GmbH",
            line2="Test Street 123",
            line3="12345 Vienna",
            line4="",
            line5="",
            line6="AT",
        ),
        timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def invalid_result() -> UidCheckResult:
    """Provide an invalid UID result (return_code != 0)."""
    return UidCheckResult(
        uid="XX999999999",
        return_code=1,
        message="UID is invalid",
        timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
    )


# ============================================================================
# Basic get/put operations
# ============================================================================


class TestCachePutGet:
    """Tests for basic cache operations."""

    def test_put_then_get_returns_cached_result(self, cache: UidResultCache, valid_result: UidCheckResult) -> None:
        """Storing a result allows retrieval with cache flags set."""
        cache.put(valid_result)

        cached = cache.get(valid_result.uid)

        assert cached is not None
        assert cached.uid == valid_result.uid
        assert cached.return_code == valid_result.return_code
        assert cached.message == valid_result.message
        assert cached.name == valid_result.name
        assert cached.from_cache is True
        assert cached.cached_at is not None

    def test_get_nonexistent_uid_returns_none(self, cache: UidResultCache) -> None:
        """Getting a UID that was never cached returns None."""
        result = cache.get("ATU99999999")
        assert result is None

    def test_invalid_result_not_cached(self, cache: UidResultCache, invalid_result: UidCheckResult) -> None:
        """Results with return_code != 0 are not cached."""
        cache.put(invalid_result)

        cached = cache.get(invalid_result.uid)
        assert cached is None

    def test_uid_normalized_on_get(self, cache: UidResultCache, valid_result: UidCheckResult) -> None:
        """UID lookup is case-insensitive and strips whitespace."""
        cache.put(valid_result)

        # Lookup with different casing and whitespace
        cached = cache.get("  atu12345678  ")

        assert cached is not None
        assert cached.uid == valid_result.uid

    def test_address_round_trip(self, cache: UidResultCache, valid_result: UidCheckResult) -> None:
        """Address data survives serialization and deserialization."""
        cache.put(valid_result)
        cached = cache.get(valid_result.uid)

        assert cached is not None
        assert cached.address is not None
        assert cached.address.line1 == "Test Company GmbH"
        assert cached.address.line2 == "Test Street 123"
        assert cached.address.line3 == "12345 Vienna"
        assert cached.address.line6 == "AT"

    def test_result_without_address(self, cache: UidResultCache) -> None:
        """Result without address can be cached and retrieved."""
        result = UidCheckResult(
            uid="ATU11111111",
            return_code=0,
            message="UID valid",
            name="No Address Company",
            address=None,
            timestamp=datetime.now(timezone.utc),
        )

        cache.put(result)
        cached = cache.get(result.uid)

        assert cached is not None
        assert cached.address is None


# ============================================================================
# Expiration handling
# ============================================================================


class TestCacheExpiration:
    """Tests for cache entry expiration."""

    def test_expired_entry_returns_none(self, cache_file: Path, valid_result: UidCheckResult) -> None:
        """Expired cache entries return None on lookup."""
        # Use a cache with very short expiry
        cache = UidResultCache(cache_file=cache_file, cache_hours=0.001)  # ~3.6 seconds
        cache.put(valid_result)

        # Simulate time passing by modifying the cache file
        data: dict[str, dict[str, object]] = orjson.loads(cache_file.read_bytes())
        uid_upper = valid_result.uid.upper()
        # Set expires_at to the past
        data[uid_upper]["expires_at"] = "2020-01-01T00:00:00Z"
        cache_file.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))

        cached = cache.get(valid_result.uid)
        assert cached is None

    def test_valid_entry_before_expiration(self, cache: UidResultCache, valid_result: UidCheckResult) -> None:
        """Entry is returned when still within expiration window."""
        cache.put(valid_result)

        # Immediately retrieve (well within 24-hour window)
        cached = cache.get(valid_result.uid)

        assert cached is not None
        assert cached.from_cache is True


# ============================================================================
# Cleanup of expired entries
# ============================================================================


class TestCacheCleanup:
    """Tests for automatic cleanup of expired entries."""

    def test_expired_entries_cleaned_on_write(self, cache_file: Path, valid_result: UidCheckResult) -> None:
        """Writing a new entry removes expired entries from cache."""
        cache = UidResultCache(cache_file=cache_file, cache_hours=24.0)

        # Pre-populate with an expired entry
        expired_data = {
            "EXPIRED123": {
                "uid": "EXPIRED123",
                "return_code": 0,
                "message": "Old entry",
                "name": "",
                "address": None,
                "queried_at": "2020-01-01T00:00:00Z",
                "expires_at": "2020-01-02T00:00:00Z",  # Long expired
            }
        }
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(orjson.dumps(expired_data, option=orjson.OPT_INDENT_2))

        # Write a new entry
        cache.put(valid_result)

        # Verify expired entry was removed
        data: dict[str, object] = orjson.loads(cache_file.read_bytes())
        assert "EXPIRED123" not in data
        assert valid_result.uid.upper() in data


# ============================================================================
# Disabled cache behavior
# ============================================================================


class TestCacheDisabled:
    """Tests for cache behavior when disabled (cache_hours=0)."""

    def test_disabled_cache_returns_none_on_get(self, cache_file: Path, valid_result: UidCheckResult) -> None:
        """Disabled cache always returns None on get."""
        cache = UidResultCache(cache_file=cache_file, cache_hours=0)

        # Pre-populate the cache file directly
        data = {
            valid_result.uid.upper(): {
                "uid": valid_result.uid,
                "return_code": 0,
                "message": "Cached",
                "name": "",
                "address": None,
                "queried_at": "2025-01-01T00:00:00Z",
                "expires_at": "2025-12-31T00:00:00Z",
            }
        }
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(orjson.dumps(data))

        # Get should return None even though data exists
        result = cache.get(valid_result.uid)
        assert result is None

    def test_disabled_cache_does_not_write(self, cache_file: Path, valid_result: UidCheckResult) -> None:
        """Disabled cache does not write to file."""
        cache = UidResultCache(cache_file=cache_file, cache_hours=0)

        cache.put(valid_result)

        assert not cache_file.exists()

    def test_is_enabled_property(self, cache_file: Path) -> None:
        """is_enabled reflects cache_hours setting."""
        enabled = UidResultCache(cache_file=cache_file, cache_hours=24.0)
        disabled = UidResultCache(cache_file=cache_file, cache_hours=0)

        assert enabled.is_enabled is True
        assert disabled.is_enabled is False


# ============================================================================
# Error handling
# ============================================================================


class TestCacheErrorHandling:
    """Tests for cache error handling."""

    def test_corrupt_json_returns_none(self, cache_file: Path) -> None:
        """Corrupt JSON file returns None without raising."""
        cache = UidResultCache(cache_file=cache_file, cache_hours=24.0)

        # Write invalid JSON
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text("{ invalid json }")

        result = cache.get("ATU12345678")

        assert result is None

    def test_missing_cache_file_returns_none(self, cache: UidResultCache) -> None:
        """Missing cache file returns None."""
        result = cache.get("ATU12345678")
        assert result is None

    def test_empty_cache_file_returns_none(self, cache: UidResultCache) -> None:
        """Empty cache file returns None."""
        cache.cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache.cache_file.write_bytes(b"")

        result = cache.get("ATU12345678")
        assert result is None


# ============================================================================
# Cache file management
# ============================================================================


class TestCacheFileManagement:
    """Tests for cache file creation and clearing."""

    def test_cache_creates_parent_directories(self, tmp_path: Path, valid_result: UidCheckResult) -> None:
        """Cache creates parent directories if they don't exist."""
        deep_path = tmp_path / "a" / "b" / "c" / "cache.json"
        cache = UidResultCache(cache_file=deep_path, cache_hours=24.0)

        cache.put(valid_result)

        assert deep_path.exists()

    def test_clear_removes_cache_file(self, cache: UidResultCache, valid_result: UidCheckResult) -> None:
        """clear() removes the cache file."""
        cache.put(valid_result)
        assert cache.cache_file.exists()

        cache.clear()

        assert not cache.cache_file.exists()

    def test_clear_on_nonexistent_file(self, cache: UidResultCache) -> None:
        """clear() handles nonexistent file gracefully."""
        # Should not raise
        cache.clear()


# ============================================================================
# Cache properties
# ============================================================================


class TestCacheProperties:
    """Tests for cache property accessors."""

    def test_cache_file_property(self, cache_file: Path) -> None:
        """cache_file property returns the configured path."""
        cache = UidResultCache(cache_file=cache_file, cache_hours=24.0)
        assert cache.cache_file == cache_file

    def test_cache_hours_property(self, cache_file: Path) -> None:
        """cache_hours property returns the configured duration."""
        cache = UidResultCache(cache_file=cache_file, cache_hours=48.0)
        assert cache.cache_hours == 48.0


# ============================================================================
# Cached result timestamp handling
# ============================================================================


class TestCachedResultTimestamp:
    """Tests for cached_at timestamp in returned results."""

    def test_cached_at_contains_original_query_time(self, cache: UidResultCache, valid_result: UidCheckResult) -> None:
        """cached_at should reflect the original query timestamp."""
        cache.put(valid_result)
        cached = cache.get(valid_result.uid)

        assert cached is not None
        assert cached.cached_at is not None
        # cached_at should be close to the original timestamp
        assert cached.cached_at.year == 2025
        assert cached.cached_at.month == 1
        assert cached.cached_at.day == 15

    def test_timestamp_is_current_time(self, cache: UidResultCache, valid_result: UidCheckResult) -> None:
        """timestamp should be the retrieval time, not original query time."""
        cache.put(valid_result)

        # Get current time before retrieval
        before = datetime.now(timezone.utc)
        cached = cache.get(valid_result.uid)
        after = datetime.now(timezone.utc)

        assert cached is not None
        # timestamp should be between before and after
        assert before <= cached.timestamp <= after
