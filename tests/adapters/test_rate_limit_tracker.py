"""Tests for rate limit tracker.

Tests cover:
- Basic record_call and get_status operations
- Sliding window behavior
- Cleanup of old entries
- Disabled rate limiter behavior
- File locking and error handling
- Clear operation
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import orjson
import pytest

from finanzonline_uid.adapters.ratelimit import PerUidRateLimitStatus, RateLimitStatus, RateLimitTracker

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def ratelimit_file(tmp_path: Path) -> Path:
    """Provide a temporary rate limit file path."""
    return tmp_path / "test_rate_limits.json"


@pytest.fixture
def tracker(ratelimit_file: Path) -> RateLimitTracker:
    """Provide a rate limit tracker with 10 queries per 24 hours."""
    return RateLimitTracker(
        ratelimit_file=ratelimit_file,
        max_queries=10,
        window_hours=24.0,
    )


# ============================================================================
# Basic record_call and get_status operations
# ============================================================================


class TestRateLimitTrackerBasics:
    """Tests for basic tracking operations."""

    def test_record_call_increments_count(self, tracker: RateLimitTracker) -> None:
        """Recording a call should increment the count."""
        status1 = tracker.record_call("DE123456789")
        assert status1.current_count == 1

        status2 = tracker.record_call("DE987654321")
        assert status2.current_count == 2

    def test_get_status_returns_current_count(self, tracker: RateLimitTracker) -> None:
        """get_status should return current count without incrementing."""
        tracker.record_call("DE123456789")
        tracker.record_call("DE987654321")

        status = tracker.get_status()

        assert status.current_count == 2
        # Calling again should not change count
        status2 = tracker.get_status()
        assert status2.current_count == 2

    def test_is_limit_exceeded_when_over_max(self, ratelimit_file: Path) -> None:
        """is_exceeded should be True when count exceeds max."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=3,
            window_hours=24.0,
        )

        # Record 3 calls - at limit but not exceeded
        tracker.record_call("UID1")
        tracker.record_call("UID2")
        status = tracker.record_call("UID3")
        assert status.is_exceeded is False
        assert status.current_count == 3

        # Record 4th call - now exceeded
        status = tracker.record_call("UID4")
        assert status.is_exceeded is True
        assert status.current_count == 4

    def test_uid_normalized_to_uppercase(self, tracker: RateLimitTracker, ratelimit_file: Path) -> None:
        """UIDs should be normalized to uppercase in storage."""
        tracker.record_call("  de123456789  ")

        data: dict[str, Any] = orjson.loads(ratelimit_file.read_bytes())
        entries: list[dict[str, str]] = data["api_calls"]
        assert len(entries) == 1
        assert entries[0]["uid"] == "DE123456789"

    def test_status_contains_all_fields(self, tracker: RateLimitTracker) -> None:
        """RateLimitStatus should contain all expected fields."""
        status = tracker.record_call("DE123456789")

        assert isinstance(status, RateLimitStatus)
        assert status.current_count == 1
        assert status.max_queries == 10
        assert status.window_hours == 24.0
        assert status.is_exceeded is False


# ============================================================================
# Sliding window behavior
# ============================================================================


class TestRateLimitSlidingWindow:
    """Tests for sliding window behavior."""

    def test_old_entries_not_counted(self, ratelimit_file: Path) -> None:
        """Entries older than window should not be counted."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=10,
            window_hours=1.0,  # 1 hour window
        )

        # Pre-populate with old entry (2 hours ago)
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        old_data: dict[str, Any] = {
            "api_calls": [{"timestamp": old_time.isoformat().replace("+00:00", "Z"), "uid": "OLD123"}],
            "metadata": {},
        }
        ratelimit_file.parent.mkdir(parents=True, exist_ok=True)
        ratelimit_file.write_bytes(orjson.dumps(old_data, option=orjson.OPT_INDENT_2))

        # Get status - old entry should not be counted
        status = tracker.get_status()
        assert status.current_count == 0

    def test_entries_within_window_are_counted(self, ratelimit_file: Path) -> None:
        """Entries within window should be counted."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=10,
            window_hours=2.0,  # 2 hour window
        )

        # Pre-populate with entry 1 hour ago (within window)
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        test_data: dict[str, Any] = {
            "api_calls": [{"timestamp": recent_time.isoformat().replace("+00:00", "Z"), "uid": "RECENT123"}],
            "metadata": {},
        }
        ratelimit_file.parent.mkdir(parents=True, exist_ok=True)
        ratelimit_file.write_bytes(orjson.dumps(test_data, option=orjson.OPT_INDENT_2))

        # Get status - recent entry should be counted
        status = tracker.get_status()
        assert status.current_count == 1


# ============================================================================
# Cleanup of old entries
# ============================================================================


class TestRateLimitCleanup:
    """Tests for automatic cleanup of old entries."""

    def test_old_entries_cleaned_on_write(self, ratelimit_file: Path) -> None:
        """Writing a new entry should remove old entries."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=10,
            window_hours=1.0,
        )

        # Pre-populate with old entry
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        old_data: dict[str, Any] = {
            "api_calls": [{"timestamp": old_time.isoformat().replace("+00:00", "Z"), "uid": "OLD123"}],
            "metadata": {},
        }
        ratelimit_file.parent.mkdir(parents=True, exist_ok=True)
        ratelimit_file.write_bytes(orjson.dumps(old_data, option=orjson.OPT_INDENT_2))

        # Record a new call
        tracker.record_call("NEW123")

        # Verify old entry was removed
        data: dict[str, Any] = orjson.loads(ratelimit_file.read_bytes())
        entries: list[dict[str, str]] = data["api_calls"]
        assert len(entries) == 1
        assert entries[0]["uid"] == "NEW123"


# ============================================================================
# Disabled rate limiter behavior
# ============================================================================


class TestRateLimitDisabled:
    """Tests for disabled rate limiter (max_queries=0)."""

    def test_disabled_returns_not_exceeded(self, ratelimit_file: Path) -> None:
        """Disabled tracker should always return is_exceeded=False."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=0,
            window_hours=24.0,
        )

        status = tracker.record_call("DE123456789")

        assert status.is_exceeded is False
        assert status.current_count == 0

    def test_disabled_does_not_write_file(self, ratelimit_file: Path) -> None:
        """Disabled tracker should not create file."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=0,
            window_hours=24.0,
        )

        tracker.record_call("DE123456789")

        assert not ratelimit_file.exists()

    def test_is_enabled_property(self, ratelimit_file: Path) -> None:
        """is_enabled reflects max_queries setting."""
        enabled = RateLimitTracker(ratelimit_file=ratelimit_file, max_queries=10, window_hours=24.0)
        disabled = RateLimitTracker(ratelimit_file=ratelimit_file, max_queries=0, window_hours=24.0)

        assert enabled.is_enabled is True
        assert disabled.is_enabled is False


# ============================================================================
# Error handling
# ============================================================================


class TestRateLimitErrorHandling:
    """Tests for error handling."""

    def test_corrupt_json_returns_zero_count(self, ratelimit_file: Path) -> None:
        """Corrupt JSON file should return zero count without raising."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=10,
            window_hours=24.0,
        )

        # Write invalid JSON
        ratelimit_file.parent.mkdir(parents=True, exist_ok=True)
        ratelimit_file.write_text("{ invalid json }")

        status = tracker.get_status()

        assert status.current_count == 0
        assert status.is_exceeded is False

    def test_missing_file_returns_zero_count(self, tracker: RateLimitTracker) -> None:
        """Missing file should return zero count."""
        status = tracker.get_status()

        assert status.current_count == 0
        assert status.is_exceeded is False

    def test_empty_file_returns_zero_count(self, tracker: RateLimitTracker) -> None:
        """Empty file should return zero count."""
        tracker.ratelimit_file.parent.mkdir(parents=True, exist_ok=True)
        tracker.ratelimit_file.write_bytes(b"")

        status = tracker.get_status()

        assert status.current_count == 0


# ============================================================================
# File management
# ============================================================================


class TestRateLimitFileManagement:
    """Tests for file creation and clearing."""

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Tracker should create parent directories if they don't exist."""
        deep_path = tmp_path / "a" / "b" / "c" / "rate_limits.json"
        tracker = RateLimitTracker(
            ratelimit_file=deep_path,
            max_queries=10,
            window_hours=24.0,
        )

        tracker.record_call("DE123456789")

        assert deep_path.exists()

    def test_clear_removes_file(self, tracker: RateLimitTracker) -> None:
        """clear() should remove the rate limit file."""
        tracker.record_call("DE123456789")
        assert tracker.ratelimit_file.exists()

        tracker.clear()

        assert not tracker.ratelimit_file.exists()

    def test_clear_handles_nonexistent_file(self, tracker: RateLimitTracker) -> None:
        """clear() should handle nonexistent file gracefully."""
        # Should not raise
        tracker.clear()


# ============================================================================
# Properties
# ============================================================================


class TestRateLimitProperties:
    """Tests for property accessors."""

    def test_ratelimit_file_property(self, ratelimit_file: Path) -> None:
        """ratelimit_file property returns the configured path."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=10,
            window_hours=24.0,
        )
        assert tracker.ratelimit_file == ratelimit_file

    def test_max_queries_property(self, ratelimit_file: Path) -> None:
        """max_queries property returns the configured limit."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=50,
            window_hours=24.0,
        )
        assert tracker.max_queries == 50

    def test_window_hours_property(self, ratelimit_file: Path) -> None:
        """window_hours property returns the configured duration."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=10,
            window_hours=48.0,
        )
        assert tracker.window_hours == 48.0


# ============================================================================
# File format verification
# ============================================================================


class TestRateLimitFileFormat:
    """Tests for file format and structure."""

    def test_file_contains_expected_structure(self, tracker: RateLimitTracker, ratelimit_file: Path) -> None:
        """File should have api_calls array and metadata object."""
        tracker.record_call("DE123456789")

        data: dict[str, Any] = orjson.loads(ratelimit_file.read_bytes())

        assert "api_calls" in data
        assert "metadata" in data
        assert isinstance(data["api_calls"], list)
        assert isinstance(data["metadata"], dict)

    def test_entries_contain_timestamp_and_uid(self, tracker: RateLimitTracker, ratelimit_file: Path) -> None:
        """Each entry should have timestamp and uid fields."""
        tracker.record_call("DE123456789")

        data: dict[str, Any] = orjson.loads(ratelimit_file.read_bytes())
        entries: list[dict[str, str]] = data["api_calls"]
        entry = entries[0]

        assert "timestamp" in entry
        assert "uid" in entry
        assert entry["uid"] == "DE123456789"
        # Verify timestamp is ISO format
        assert "T" in entry["timestamp"]

    def test_metadata_contains_last_cleanup(self, tracker: RateLimitTracker, ratelimit_file: Path) -> None:
        """Metadata should contain last_cleanup timestamp."""
        tracker.record_call("DE123456789")

        data: dict[str, Any] = orjson.loads(ratelimit_file.read_bytes())
        metadata: dict[str, str] = data["metadata"]

        assert "last_cleanup" in metadata
        assert "T" in metadata["last_cleanup"]


# ============================================================================
# Max entries limit
# ============================================================================


class TestRateLimitMaxEntries:
    """Tests for max entries limit."""

    def test_max_entries_property(self, ratelimit_file: Path) -> None:
        """max_entries property returns the configured limit."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=10,
            window_hours=24.0,
            max_entries=500,
        )
        assert tracker.max_entries == 500

    def test_max_entries_default(self, ratelimit_file: Path) -> None:
        """max_entries defaults to 10000."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=10,
            window_hours=24.0,
        )
        assert tracker.max_entries == 10000

    def test_oldest_entries_trimmed_when_limit_exceeded(self, ratelimit_file: Path) -> None:
        """Oldest entries are removed when max_entries is exceeded."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=100,
            window_hours=24.0,
            max_entries=3,
        )

        # Pre-populate with 3 entries (at the limit)
        now = datetime.now(timezone.utc)
        existing_data: dict[str, Any] = {
            "api_calls": [
                {"timestamp": (now - timedelta(hours=3)).isoformat().replace("+00:00", "Z"), "uid": "UID001"},  # Oldest
                {"timestamp": (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"), "uid": "UID002"},
                {"timestamp": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"), "uid": "UID003"},  # Newest
            ],
            "metadata": {},
        }
        ratelimit_file.parent.mkdir(parents=True, exist_ok=True)
        ratelimit_file.write_bytes(orjson.dumps(existing_data, option=orjson.OPT_INDENT_2))

        # Add a new entry, which should trigger trimming of the oldest
        tracker.record_call("UID004")

        # Verify: should have 3 entries, oldest (UID001) removed
        data: dict[str, Any] = orjson.loads(ratelimit_file.read_bytes())
        entries: list[dict[str, str]] = data["api_calls"]
        uids = [e["uid"] for e in entries]

        assert len(entries) == 3
        assert "UID001" not in uids  # Oldest was trimmed
        assert "UID002" in uids
        assert "UID003" in uids
        assert "UID004" in uids


# ============================================================================
# Per-UID rate limiting
# ============================================================================


class TestPerUidRateLimiting:
    """Tests for per-UID rate limiting."""

    def test_per_uid_limit_property(self, ratelimit_file: Path) -> None:
        """per_uid_limit property returns the configured limit."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=10,
            window_hours=24.0,
            per_uid_limit=5,
        )
        assert tracker.per_uid_limit == 5

    def test_per_uid_limit_default(self, ratelimit_file: Path) -> None:
        """per_uid_limit defaults to 2 (BMF limit)."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=10,
            window_hours=24.0,
        )
        assert tracker.per_uid_limit == 2

    def test_get_uid_status_returns_count(self, ratelimit_file: Path) -> None:
        """get_uid_status returns count for specific UID."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=100,
            window_hours=24.0,
        )

        # Record multiple calls with different UIDs
        tracker.record_call("DE111111111")
        tracker.record_call("DE222222222")
        tracker.record_call("DE111111111")  # Second call for this UID

        status = tracker.get_uid_status("DE111111111")

        assert isinstance(status, PerUidRateLimitStatus)
        assert status.uid == "DE111111111"
        assert status.uid_count == 2
        assert status.per_uid_limit == 2
        assert status.is_uid_exceeded is True  # 2 >= 2

    def test_get_uid_status_normalizes_uid(self, ratelimit_file: Path) -> None:
        """get_uid_status normalizes UID to uppercase."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=100,
            window_hours=24.0,
        )

        tracker.record_call("DE111111111")

        # Query with different casing and whitespace
        status = tracker.get_uid_status("  de111111111  ")

        assert status.uid == "DE111111111"
        assert status.uid_count == 1

    def test_get_uid_status_not_exceeded_under_limit(self, ratelimit_file: Path) -> None:
        """get_uid_status shows not exceeded when under limit."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=100,
            window_hours=24.0,
            per_uid_limit=3,
        )

        tracker.record_call("DE111111111")

        status = tracker.get_uid_status("DE111111111")

        assert status.uid_count == 1
        assert status.per_uid_limit == 3
        assert status.is_uid_exceeded is False

    def test_get_uid_status_returns_zero_for_unknown_uid(self, ratelimit_file: Path) -> None:
        """get_uid_status returns zero count for never-seen UID."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=100,
            window_hours=24.0,
        )

        tracker.record_call("DE111111111")

        status = tracker.get_uid_status("DE999999999")

        assert status.uid_count == 0
        assert status.is_uid_exceeded is False

    def test_get_uid_status_disabled_returns_not_exceeded(self, ratelimit_file: Path) -> None:
        """get_uid_status returns not exceeded when tracking is disabled."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=0,  # Disabled
            window_hours=24.0,
        )

        status = tracker.get_uid_status("DE111111111")

        assert status.uid_count == 0
        assert status.is_uid_exceeded is False

    def test_get_uid_status_zero_per_uid_limit_not_exceeded(self, ratelimit_file: Path) -> None:
        """get_uid_status returns not exceeded when per_uid_limit is 0."""
        tracker = RateLimitTracker(
            ratelimit_file=ratelimit_file,
            max_queries=10,
            window_hours=24.0,
            per_uid_limit=0,
        )

        status = tracker.get_uid_status("DE111111111")

        assert status.is_uid_exceeded is False


# ============================================================================
# On-disk wire format (shared with already-installed versions)
# ============================================================================

# Bytes an installed version writes after two calls. Installed versions read
# and rewrite this file too, so it must load unchanged and survive a rewrite
# byte for byte.
_INSTALLED_RATELIMIT_BYTES = (
    b"{\n"
    b'  "api_calls": [\n'
    b"    {\n"
    b'      "timestamp": "2025-01-15T10:30:00.123456Z",\n'
    b'      "uid": "DE123456789"\n'
    b"    },\n"
    b"    {\n"
    b'      "timestamp": "2025-01-16T08:00:00Z",\n'
    b'      "uid": "ATU11111111"\n'
    b"    }\n"
    b"  ],\n"
    b'  "metadata": {\n'
    b'    "last_cleanup": "2025-01-16T08:00:00.000001Z"\n'
    b"  }\n"
    b"}"
)

_EXPECTED_AFTER_RECORD = (
    b"{\n"
    b'  "api_calls": [\n'
    b"    {\n"
    b'      "timestamp": "2025-01-15T10:30:00.123456Z",\n'
    b'      "uid": "DE123456789"\n'
    b"    },\n"
    b"    {\n"
    b'      "timestamp": "2025-01-16T08:00:00Z",\n'
    b'      "uid": "ATU11111111"\n'
    b"    },\n"
    b"    {\n"
    b'      "timestamp": "__NEW_TIMESTAMP__",\n'
    b'      "uid": "ATU33333333"\n'
    b"    }\n"
    b"  ],\n"
    b'  "metadata": {\n'
    b'    "last_cleanup": "__LAST_CLEANUP__"\n'
    b"  }\n"
    b"}"
)

# Wide enough that the 2025 entries above stay inside the sliding window.
_CENTURY_HOURS = 1_000_000.0


def _century_tracker(ratelimit_file: Path) -> RateLimitTracker:
    return RateLimitTracker(ratelimit_file=ratelimit_file, max_queries=50, window_hours=_CENTURY_HOURS)


def _write_raw(ratelimit_file: Path, content: bytes) -> None:
    ratelimit_file.parent.mkdir(parents=True, exist_ok=True)
    ratelimit_file.write_bytes(content)


def _stored_calls(ratelimit_file: Path) -> list[dict[str, str]]:
    data: dict[str, Any] = orjson.loads(ratelimit_file.read_bytes())
    calls: list[dict[str, str]] = data["api_calls"]
    return calls


class TestRateLimitWireFormat:
    """The rate-limit file is a wire shared with installed versions."""

    def test_installed_file_is_counted(self, ratelimit_file: Path) -> None:
        """Both calls in an installed file are inside the window."""
        _write_raw(ratelimit_file, _INSTALLED_RATELIMIT_BYTES)
        tracker = _century_tracker(ratelimit_file)

        assert tracker.get_status().current_count == 2
        assert tracker.get_uid_status("de123456789").uid_count == 1

    def test_record_call_rewrites_installed_file_byte_for_byte(self, ratelimit_file: Path) -> None:
        """record_call keeps installed entries' bytes and appends in the same form."""
        _write_raw(ratelimit_file, _INSTALLED_RATELIMIT_BYTES)
        tracker = _century_tracker(ratelimit_file)

        status = tracker.record_call("atu33333333")

        data: dict[str, Any] = orjson.loads(ratelimit_file.read_bytes())
        new_timestamp: str = data["api_calls"][2]["timestamp"]
        last_cleanup: str = data["metadata"]["last_cleanup"]
        assert new_timestamp.endswith("Z")
        assert last_cleanup.endswith("Z")
        expected = _EXPECTED_AFTER_RECORD.replace(b"__NEW_TIMESTAMP__", new_timestamp.encode()).replace(b"__LAST_CLEANUP__", last_cleanup.encode())
        assert ratelimit_file.read_bytes() == expected
        assert status.current_count == 3


class TestRateLimitMalformedContent:
    """Malformed files reset and malformed entries are skipped, as installed versions do."""

    @pytest.mark.parametrize("content", [b"[1, 2]", b'"text"', b"42", b"null", b'{"metadata": {}}', b'{"api_calls": "x"}'])
    def test_unusable_file_counts_zero_and_is_reset(self, ratelimit_file: Path, content: bytes) -> None:
        """A file without a usable api_calls list counts nothing and is rewritten with the new call only."""
        _write_raw(ratelimit_file, content)
        tracker = _century_tracker(ratelimit_file)

        assert tracker.get_status().current_count == 0
        tracker.record_call("ATU33333333")

        assert [c["uid"] for c in _stored_calls(ratelimit_file)] == ["ATU33333333"]

    @pytest.mark.parametrize(
        "bad_call",
        [
            {"uid": "NOTIME"},
            {"timestamp": "not-a-date", "uid": "BADTIME"},
            {"timestamp": "", "uid": "EMPTYTIME"},
            {"timestamp": 1736985600, "uid": "NUMTIME"},
        ],
    )
    def test_malformed_call_is_skipped(self, ratelimit_file: Path, bad_call: dict[str, object]) -> None:
        """A call without a parsable timestamp is not counted and is dropped on write."""
        good_call = {"timestamp": "2025-01-16T08:00:00Z", "uid": "GOOD"}
        _write_raw(ratelimit_file, orjson.dumps({"api_calls": [bad_call, good_call], "metadata": {}}))
        tracker = _century_tracker(ratelimit_file)

        assert tracker.get_status().current_count == 1
        tracker.record_call("ATU33333333")

        assert [c["uid"] for c in _stored_calls(ratelimit_file)] == ["GOOD", "ATU33333333"]

    def test_call_without_uid_is_counted_with_empty_uid(self, ratelimit_file: Path) -> None:
        """uid is optional; a call without it still counts and is written back with an empty uid."""
        _write_raw(ratelimit_file, orjson.dumps({"api_calls": [{"timestamp": "2025-01-16T08:00:00Z"}]}))
        tracker = _century_tracker(ratelimit_file)

        assert tracker.get_status().current_count == 1
        tracker.record_call("ATU33333333")

        calls = _stored_calls(ratelimit_file)
        assert calls[0] == {"timestamp": "2025-01-16T08:00:00Z", "uid": ""}

    def test_missing_metadata_is_written(self, ratelimit_file: Path) -> None:
        """A file without metadata gains metadata.last_cleanup on write."""
        _write_raw(ratelimit_file, b'{"api_calls": []}')

        _century_tracker(ratelimit_file).record_call("ATU33333333")

        data: dict[str, Any] = orjson.loads(ratelimit_file.read_bytes())
        assert list(data) == ["api_calls", "metadata"]
        assert list(data["metadata"]) == ["last_cleanup"]

    @pytest.mark.parametrize("bad_call", ["garbage", 7, None, ["2025-01-16T08:00:00Z"]])
    def test_non_object_call_is_skipped(self, ratelimit_file: Path, bad_call: object) -> None:
        """A call that is not a JSON object is not counted and is dropped on write."""
        good_call = {"timestamp": "2025-01-16T08:00:00Z", "uid": "GOOD"}
        _write_raw(ratelimit_file, orjson.dumps({"api_calls": [bad_call, good_call]}))
        tracker = _century_tracker(ratelimit_file)

        assert tracker.get_status().current_count == 1
        tracker.record_call("ATU33333333")

        assert [c["uid"] for c in _stored_calls(ratelimit_file)] == ["GOOD", "ATU33333333"]

    def test_unusable_metadata_is_replaced(self, ratelimit_file: Path) -> None:
        """metadata that is not an object is replaced by a fresh one on write."""
        _write_raw(ratelimit_file, b'{"api_calls": [], "metadata": [1]}')

        _century_tracker(ratelimit_file).record_call("ATU33333333")

        data: dict[str, Any] = orjson.loads(ratelimit_file.read_bytes())
        assert list(data["metadata"]) == ["last_cleanup"]

    def test_naive_timestamp_is_read_as_utc(self, ratelimit_file: Path) -> None:
        """A timestamp without an offset is read as UTC, the convention format_iso_datetime writes."""
        _write_raw(ratelimit_file, orjson.dumps({"api_calls": [{"timestamp": "2025-01-16T08:00:00", "uid": "NAIVE"}]}))
        tracker = _century_tracker(ratelimit_file)

        assert tracker.get_status().current_count == 1

    def test_corrupt_json_on_record_raises(self, ratelimit_file: Path) -> None:
        """An unparsable file is not silently overwritten by record_call."""
        _write_raw(ratelimit_file, b"{ invalid json }")

        with pytest.raises(orjson.JSONDecodeError):
            _century_tracker(ratelimit_file).record_call("ATU33333333")

        assert ratelimit_file.read_bytes() == b"{ invalid json }"
