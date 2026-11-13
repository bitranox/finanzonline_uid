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

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import orjson
import pytest
from filelock import FileLock

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

    def test_max_entries_property(self, cache_file: Path) -> None:
        """max_entries property returns the configured limit."""
        cache = UidResultCache(cache_file=cache_file, cache_hours=24.0, max_entries=500)
        assert cache.max_entries == 500

    def test_max_entries_default(self, cache_file: Path) -> None:
        """max_entries defaults to 1000."""
        cache = UidResultCache(cache_file=cache_file, cache_hours=24.0)
        assert cache.max_entries == 1000


# ============================================================================
# Max entries limit
# ============================================================================


class TestCacheMaxEntries:
    """Tests for cache max entries limit."""

    def test_oldest_entries_trimmed_when_limit_exceeded(self, cache_file: Path) -> None:
        """Oldest entries are removed when max_entries is exceeded."""
        cache = UidResultCache(cache_file=cache_file, cache_hours=24.0, max_entries=3)

        # Calculate dynamic timestamps to avoid test brittleness
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Pre-populate with 3 entries (at the limit)
        existing_data = {
            "UID001": {
                "uid": "UID001",
                "return_code": 0,
                "message": "Valid",
                "name": "",
                "address": None,
                "queried_at": (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),  # Oldest
                "expires_at": expires_at,
            },
            "UID002": {
                "uid": "UID002",
                "return_code": 0,
                "message": "Valid",
                "name": "",
                "address": None,
                "queried_at": (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),  # Middle
                "expires_at": expires_at,
            },
            "UID003": {
                "uid": "UID003",
                "return_code": 0,
                "message": "Valid",
                "name": "",
                "address": None,
                "queried_at": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),  # Newest
                "expires_at": expires_at,
            },
        }
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(orjson.dumps(existing_data, option=orjson.OPT_INDENT_2))

        # Add a new entry, which should trigger trimming of the oldest
        new_result = UidCheckResult(
            uid="UID004",
            return_code=0,
            message="Valid",
            timestamp=datetime.now(timezone.utc),
        )
        cache.put(new_result)

        # Verify: should have 3 entries, oldest (UID001) removed
        data: dict[str, object] = orjson.loads(cache_file.read_bytes())
        assert len(data) == 3
        assert "UID001" not in data  # Oldest was trimmed
        assert "UID002" in data
        assert "UID003" in data
        assert "UID004" in data

    def test_entries_not_trimmed_when_under_limit(self, cache_file: Path) -> None:
        """No entries trimmed when under max_entries limit."""
        cache = UidResultCache(cache_file=cache_file, cache_hours=24.0, max_entries=10)

        # Add a few entries (under limit)
        for i in range(3):
            result = UidCheckResult(
                uid=f"ATU{i:08d}",
                return_code=0,
                message="Valid",
                timestamp=datetime.now(timezone.utc),
            )
            cache.put(result)

        data: dict[str, object] = orjson.loads(cache_file.read_bytes())
        assert len(data) == 3


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

    def test_timestamp_is_original_query_time(self, cache: UidResultCache, valid_result: UidCheckResult) -> None:
        """timestamp should be the original query time, not retrieval time."""
        cache.put(valid_result)
        cached = cache.get(valid_result.uid)

        assert cached is not None
        # timestamp should equal the original query time (cached_at)
        assert cached.timestamp == cached.cached_at
        # And should match the original result's timestamp
        assert cached.timestamp == valid_result.timestamp


# ============================================================================
# On-disk wire format (shared with already-installed versions)
# ============================================================================

# Bytes an installed version writes for two entries: one with an address, a
# microsecond timestamp and non-ASCII text, one without an address. The cache
# file is read and rewritten by every version in the field, so these bytes
# must load unchanged and survive a rewrite byte for byte.
_INSTALLED_CACHE_BYTES = (
    b"{\n"
    b'  "ATU11111111": {\n'
    b'    "uid": "ATU11111111",\n'
    b'    "return_code": 0,\n'
    b'    "message": "G\xc3\xbcltig",\n'
    b'    "name": "Firma GmbH",\n'
    b'    "address": {\n'
    b'      "line1": "Firma GmbH",\n'
    b'      "line2": "Hauptstr. 1",\n'
    b'      "line3": "1010 Wien",\n'
    b'      "line4": "",\n'
    b'      "line5": "",\n'
    b'      "line6": "AT"\n'
    b"    },\n"
    b'    "queried_at": "2025-01-15T10:30:00.123456Z",\n'
    b'    "expires_at": "2099-01-01T00:00:00Z"\n'
    b"  },\n"
    b'  "DE222222222": {\n'
    b'    "uid": "DE222222222",\n'
    b'    "return_code": 0,\n'
    b'    "message": "valid",\n'
    b'    "name": "",\n'
    b'    "address": null,\n'
    b'    "queried_at": "2025-01-16T08:00:00Z",\n'
    b'    "expires_at": "2099-01-01T00:00:00Z"\n'
    b"  }\n"
    b"}"
)

_EXPECTED_AFTER_PUT = (
    _INSTALLED_CACHE_BYTES[:-2]
    + b",\n"
    + b'  "ATU33333333": {\n'
    + b'    "uid": "ATU33333333",\n'
    + b'    "return_code": 0,\n'
    + b'    "message": "ok",\n'
    + b'    "name": "Neu",\n'
    + b'    "address": {\n'
    + b'      "line1": "Neu",\n'
    + b'      "line2": "",\n'
    + b'      "line3": "8010 Graz",\n'
    + b'      "line4": "",\n'
    + b'      "line5": "",\n'
    + b'      "line6": ""\n'
    + b"    },\n"
    + b'    "queried_at": "2025-02-01T12:00:00Z",\n'
    + b'    "expires_at": "__EXPIRES__"\n'
    + b"  }\n"
    + b"}"
)


def _write_installed_cache(cache_file: Path) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(_INSTALLED_CACHE_BYTES)


def _new_result() -> UidCheckResult:
    return UidCheckResult(
        uid="ATU33333333",
        return_code=0,
        message="ok",
        name="Neu",
        address=Address(line1="Neu", line3="8010 Graz"),
        timestamp=datetime(2025, 2, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


def _stored_entry(cache_file: Path, uid: str) -> dict[str, object]:
    data: dict[str, dict[str, object]] = orjson.loads(cache_file.read_bytes())
    return data[uid]


class TestCacheWireFormat:
    """The cache file is a wire shared with installed versions."""

    def test_installed_file_loads_with_every_field(self, cache_file: Path, cache: UidResultCache) -> None:
        """A file written by an installed version yields the stored values."""
        _write_installed_cache(cache_file)

        cached = cache.get("ATU11111111")

        assert cached is not None
        assert cached.message == "G\u00fcltig"
        assert cached.name == "Firma GmbH"
        assert cached.address == Address(line1="Firma GmbH", line2="Hauptstr. 1", line3="1010 Wien", line6="AT")
        assert cached.timestamp == datetime(2025, 1, 15, 10, 30, 0, 123456, tzinfo=timezone.utc)
        assert cached.cached_at == cached.timestamp

    def test_installed_file_entry_without_address(self, cache_file: Path, cache: UidResultCache) -> None:
        """A null address loads as None."""
        _write_installed_cache(cache_file)

        cached = cache.get("DE222222222")

        assert cached is not None
        assert cached.address is None
        assert cached.message == "valid"

    def test_put_rewrites_installed_entries_byte_for_byte(self, cache_file: Path, cache: UidResultCache) -> None:
        """put keeps installed entries' bytes and appends the new entry in the same form."""
        _write_installed_cache(cache_file)

        cache.put(_new_result())

        written = cache_file.read_bytes()
        expires = _stored_entry(cache_file, "ATU33333333")["expires_at"]
        assert isinstance(expires, str)
        assert expires.endswith("Z")
        assert written == _EXPECTED_AFTER_PUT.replace(b"__EXPIRES__", expires.encode())


class TestCacheMalformedContent:
    """Malformed files reset and malformed entries are skipped, as installed versions do."""

    @pytest.mark.parametrize("content", [b"[1, 2]", b'"text"', b"42", b"null"])
    def test_non_object_file_is_reset_on_put(self, cache_file: Path, cache: UidResultCache, content: bytes) -> None:
        """A top-level value that is not an object is replaced by the new entry alone."""
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(content)

        assert cache.get("ATU33333333") is None
        cache.put(_new_result())

        data: dict[str, object] = orjson.loads(cache_file.read_bytes())
        assert list(data) == ["ATU33333333"]

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("queried_at", None),
            ("expires_at", "not-a-date"),
            ("return_code", "abc"),
            ("uid", None),
            ("expires_at", 12345),
            ("address", "garbage"),
        ],
    )
    def test_malformed_entry_is_skipped(self, cache_file: Path, cache: UidResultCache, field: str, value: object) -> None:
        """An entry with a missing or unparsable required field is a miss and is dropped on write."""
        entry: dict[str, object] = {
            "uid": "ATU99999999",
            "return_code": 0,
            "message": "m",
            "name": "",
            "address": None,
            "queried_at": "2025-01-01T00:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
        }
        if value is None:
            del entry[field]
        else:
            entry[field] = value
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(orjson.dumps({"ATU99999999": entry}))

        assert cache.get("ATU99999999") is None
        cache.put(_new_result())

        data: dict[str, object] = orjson.loads(cache_file.read_bytes())
        assert list(data) == ["ATU33333333"]

    def test_entry_without_optional_fields_loads_with_defaults(self, cache_file: Path, cache: UidResultCache) -> None:
        """message, name and address are optional and default to empty / None."""
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(
            orjson.dumps(
                {
                    "ATU99999999": {
                        "uid": "ATU99999999",
                        "return_code": 0,
                        "queried_at": "2025-01-01T00:00:00Z",
                        "expires_at": "2099-01-01T00:00:00Z",
                    }
                }
            )
        )

        cached = cache.get("ATU99999999")

        assert cached is not None
        assert (cached.message, cached.name, cached.address) == ("", "", None)

    def test_partial_address_fills_missing_lines(self, cache_file: Path, cache: UidResultCache) -> None:
        """Address lines missing from the file read as empty strings."""
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(
            orjson.dumps(
                {
                    "ATU99999999": {
                        "uid": "ATU99999999",
                        "return_code": 0,
                        "address": {"line3": "1010 Wien"},
                        "queried_at": "2025-01-01T00:00:00Z",
                        "expires_at": "2099-01-01T00:00:00Z",
                    }
                }
            )
        )

        cached = cache.get("ATU99999999")

        assert cached is not None
        assert cached.address == Address(line3="1010 Wien")

    def test_non_object_entry_is_skipped(self, cache_file: Path, cache: UidResultCache) -> None:
        """An entry that is not a JSON object is a miss and is dropped on write."""
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(orjson.dumps({"ATU99999999": "garbage"}))

        assert cache.get("ATU99999999") is None
        cache.put(_new_result())

        data: dict[str, object] = orjson.loads(cache_file.read_bytes())
        assert list(data) == ["ATU33333333"]

    def test_expired_entry_kept_out_while_valid_neighbour_survives(self, cache_file: Path, cache: UidResultCache) -> None:
        """Cleanup on write drops expired entries and keeps unexpired ones in file order."""
        _write_installed_cache(cache_file)
        data: dict[str, dict[str, object]] = orjson.loads(cache_file.read_bytes())
        data["DE222222222"]["expires_at"] = "2020-01-01T00:00:00Z"
        cache_file.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))

        cache.put(_new_result())

        written: dict[str, object] = orjson.loads(cache_file.read_bytes())
        assert list(written) == ["ATU11111111", "ATU33333333"]

    def test_re_put_keeps_the_uid_in_its_file_position(self, cache_file: Path, cache: UidResultCache) -> None:
        """Replacing an existing UID updates it in place rather than moving it to the end."""
        _write_installed_cache(cache_file)
        refreshed = UidCheckResult(
            uid="ATU11111111",
            return_code=0,
            message="refreshed",
            timestamp=datetime(2025, 3, 1, tzinfo=timezone.utc),
        )

        cache.put(refreshed)

        written: dict[str, dict[str, object]] = orjson.loads(cache_file.read_bytes())
        assert list(written) == ["ATU11111111", "DE222222222"]
        assert written["ATU11111111"]["message"] == "refreshed"

    def test_trim_writes_oldest_first(self, cache_file: Path) -> None:
        """Above max_entries the kept entries are written oldest query first."""
        _write_installed_cache(cache_file)
        cache = UidResultCache(cache_file=cache_file, cache_hours=24.0, max_entries=2)
        older = UidCheckResult(uid="ATU33333333", return_code=0, message="ok", timestamp=datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc))

        cache.put(older)

        written: dict[str, object] = orjson.loads(cache_file.read_bytes())
        assert list(written) == ["ATU33333333", "DE222222222"]

    def test_naive_timestamp_is_read_as_utc(self, cache_file: Path, cache: UidResultCache) -> None:
        """A timestamp without an offset is read as UTC, the convention format_iso_datetime writes."""
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(
            orjson.dumps(
                {
                    "ATU99999999": {
                        "uid": "ATU99999999",
                        "return_code": 0,
                        "queried_at": "2025-01-01T00:00:00",
                        "expires_at": "2099-01-01T00:00:00",
                    }
                }
            )
        )

        cached = cache.get("ATU99999999")

        assert cached is not None
        assert cached.timestamp == datetime(2025, 1, 1, tzinfo=timezone.utc)


# ============================================================================
# A write to a file that is not valid JSON
# ============================================================================

_CORRUPT_BYTES = b"{ invalid json \xff"

# What put writes into a fresh file for _new_result(): the same form as the
# appended entry in _EXPECTED_AFTER_PUT, alone in the object.
_EXPECTED_FRESH_FILE = (
    b"{\n"
    b'  "ATU33333333": {\n'
    b'    "uid": "ATU33333333",\n'
    b'    "return_code": 0,\n'
    b'    "message": "ok",\n'
    b'    "name": "Neu",\n'
    b'    "address": {\n'
    b'      "line1": "Neu",\n'
    b'      "line2": "",\n'
    b'      "line3": "8010 Graz",\n'
    b'      "line4": "",\n'
    b'      "line5": "",\n'
    b'      "line6": ""\n'
    b"    },\n"
    b'    "queried_at": "2025-02-01T12:00:00Z",\n'
    b'    "expires_at": "__EXPIRES__"\n'
    b"  }\n"
    b"}"
)


def _aside_files(cache_file: Path) -> list[Path]:
    return sorted(cache_file.parent.glob(f"{cache_file.name}.corrupt-*"))


def _aside_stamp(aside: Path, cache_file: Path) -> datetime:
    stamp = aside.name.removeprefix(f"{cache_file.name}.corrupt-")
    return datetime.strptime(stamp, "%Y-%m-%dT%H-%M-%S.%fZ").replace(tzinfo=timezone.utc)


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING]


class TestCacheCorruptFileOnWrite:
    """put keeps an unparsable file's bytes aside and starts a fresh file instead of failing."""

    def test_put_keeps_the_bytes_aside_and_writes_the_new_entry_alone(self, cache_file: Path, cache: UidResultCache, caplog: pytest.LogCaptureFixture) -> None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(_CORRUPT_BYTES)
        before = datetime.now(timezone.utc).replace(microsecond=0)

        with caplog.at_level(logging.DEBUG):
            cache.put(_new_result())

        after = datetime.now(timezone.utc)
        expires = _stored_entry(cache_file, "ATU33333333")["expires_at"]
        assert isinstance(expires, str)
        assert cache_file.read_bytes() == _EXPECTED_FRESH_FILE.replace(b"__EXPIRES__", expires.encode())
        asides = _aside_files(cache_file)
        assert len(asides) == 1
        assert asides[0].read_bytes() == _CORRUPT_BYTES
        assert before <= _aside_stamp(asides[0], cache_file) <= after
        warnings = _warnings(caplog)
        assert len(warnings) == 1
        assert str(cache_file) in warnings[0] and str(asides[0]) in warnings[0]
        assert cache.get("ATU33333333") is not None

    def test_a_second_put_sets_nothing_else_aside(self, cache_file: Path, cache: UidResultCache) -> None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(_CORRUPT_BYTES)

        cache.put(_new_result())
        cache.put(UidCheckResult(uid="DE222222222", return_code=0, message="ok", timestamp=datetime.now(timezone.utc)))

        assert len(_aside_files(cache_file)) == 1
        assert list(orjson.loads(cache_file.read_bytes())) == ["ATU33333333", "DE222222222"]

    def test_the_move_waits_for_the_cache_lock(self, cache_file: Path, cache: UidResultCache) -> None:
        # Another writer holding the lock must see the file where it was until it lets go.
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(_CORRUPT_BYTES)
        held = FileLock(cache_file.with_suffix(".lock"))
        held.acquire()
        writer = threading.Thread(target=cache.put, args=(_new_result(),))
        try:
            writer.start()
            time.sleep(0.3)
            assert cache_file.read_bytes() == _CORRUPT_BYTES
            assert _aside_files(cache_file) == []
        finally:
            held.release()
            writer.join(timeout=30)

        assert not writer.is_alive()
        assert len(_aside_files(cache_file)) == 1

    def test_get_still_reads_a_corrupt_file_as_a_miss_and_leaves_it(self, cache_file: Path, cache: UidResultCache) -> None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(_CORRUPT_BYTES)

        assert cache.get("ATU33333333") is None
        assert cache_file.read_bytes() == _CORRUPT_BYTES
        assert _aside_files(cache_file) == []
