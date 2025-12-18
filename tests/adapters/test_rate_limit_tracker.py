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

from uid_check_austria.adapters.ratelimit import RateLimitStatus, RateLimitTracker


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
