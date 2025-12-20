"""Tests for output formatters.

Tests cover human-readable and JSON formatting of UID check results.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from finanzonline_uid.adapters.output.formatters import format_human, format_json
from finanzonline_uid.domain.models import Address, UidCheckResult


@pytest.fixture
def valid_result() -> UidCheckResult:
    """Valid UID check result fixture."""
    return UidCheckResult(
        uid="DE123456789",
        return_code=0,
        message="UID is valid",
        name="Test Company GmbH",
        address=Address(line1="Test Company GmbH", line2="Street 1", line3="12345 City"),
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def invalid_result() -> UidCheckResult:
    """Invalid UID check result fixture."""
    return UidCheckResult(
        uid="XX123456789",
        return_code=1,
        message="UID is invalid",
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def error_result() -> UidCheckResult:
    """Error UID check result fixture."""
    return UidCheckResult(
        uid="DE123456789",
        return_code=1513,
        message="Rate limit exceeded",
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


class TestFormatHuman:
    """Tests for format_human function."""

    def test_contains_uid(self, valid_result: UidCheckResult) -> None:
        """Should include UID in output."""
        output = format_human(valid_result)
        assert "DE123456789" in output

    def test_contains_status_valid(self, valid_result: UidCheckResult) -> None:
        """Should show VALID status for return code 0."""
        output = format_human(valid_result)
        assert "VALID" in output

    def test_contains_status_invalid(self, invalid_result: UidCheckResult) -> None:
        """Should show INVALID status for return code 1."""
        output = format_human(invalid_result)
        assert "INVALID" in output

    def test_contains_return_code(self, valid_result: UidCheckResult) -> None:
        """Should include return code."""
        output = format_human(valid_result)
        assert "Return Code: 0" in output

    def test_contains_message(self, valid_result: UidCheckResult) -> None:
        """Should include message."""
        output = format_human(valid_result)
        assert "UID is valid" in output

    def test_contains_timestamp(self, valid_result: UidCheckResult) -> None:
        """Should include timestamp in local time format."""
        output = format_human(valid_result)
        # Verify timestamp is present (exact time varies by timezone)
        assert "Timestamp:" in output
        # UTC suffix should not be present (now using local time)
        assert "UTC" not in output

    def test_contains_company_info_when_valid(self, valid_result: UidCheckResult) -> None:
        """Should include company info for valid results."""
        output = format_human(valid_result)
        assert "Test Company GmbH" in output
        assert "Street 1" in output
        assert "12345 City" in output

    def test_no_company_info_when_invalid(self, invalid_result: UidCheckResult) -> None:
        """Should not include company section for invalid results."""
        output = format_human(invalid_result)
        assert "Company Information" not in output

    def test_contains_severity(self, error_result: UidCheckResult) -> None:
        """Should include severity."""
        output = format_human(error_result)
        assert "WARNING" in output

    def test_contains_retryable(self, error_result: UidCheckResult) -> None:
        """Should indicate retryable status."""
        output = format_human(error_result)
        assert "Retryable:" in output
        assert "Yes" in output


class TestFormatJson:
    """Tests for format_json function."""

    def test_valid_json(self, valid_result: UidCheckResult) -> None:
        """Should produce valid JSON."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_contains_uid(self, valid_result: UidCheckResult) -> None:
        """Should include uid field."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert data["uid"] == "DE123456789"

    def test_contains_is_valid(self, valid_result: UidCheckResult) -> None:
        """Should include is_valid field."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert data["is_valid"] is True

    def test_invalid_is_valid_false(self, invalid_result: UidCheckResult) -> None:
        """Should set is_valid false for invalid results."""
        output = format_json(invalid_result)
        data = json.loads(output)
        assert data["is_valid"] is False

    def test_contains_return_code(self, valid_result: UidCheckResult) -> None:
        """Should include return_code field."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert data["return_code"] == 0

    def test_contains_message(self, valid_result: UidCheckResult) -> None:
        """Should include message field."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert data["message"] == "UID is valid"

    def test_contains_severity(self, valid_result: UidCheckResult) -> None:
        """Should include severity field."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert data["severity"] == "success"

    def test_contains_retryable(self, error_result: UidCheckResult) -> None:
        """Should include retryable field."""
        output = format_json(error_result)
        data = json.loads(output)
        assert data["retryable"] is True

    def test_contains_timestamp(self, valid_result: UidCheckResult) -> None:
        """Should include ISO format timestamp."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert data["timestamp"] == "2025-01-01T12:00:00+00:00"

    def test_contains_company_info_when_valid(self, valid_result: UidCheckResult) -> None:
        """Should include company object for valid results."""
        output = format_json(valid_result)
        data = json.loads(output)
        assert "company" in data
        assert data["company"]["name"] == "Test Company GmbH"
        assert "address" in data["company"]
        assert data["company"]["address"]["lines"] == ["Test Company GmbH", "Street 1", "12345 City"]

    def test_no_company_info_when_invalid(self, invalid_result: UidCheckResult) -> None:
        """Should not include company for invalid results."""
        output = format_json(invalid_result)
        data = json.loads(output)
        assert "company" not in data
