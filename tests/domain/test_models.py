"""Tests for domain models.

Tests cover immutability, validation, and property behavior of
all domain model dataclasses.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from uid_check_austria.domain.models import (
    Address,
    FinanzOnlineCredentials,
    SessionInfo,
    UidCheckRequest,
    UidCheckResult,
)


class TestFinanzOnlineCredentials:
    """Tests for FinanzOnlineCredentials dataclass.

    XSD validation rules (from login.xsd):
        - tid: pattern [0-9A-Za-z]{8,12}
        - benid: minLength 5, maxLength 12
        - pin: minLength 5, maxLength 128
        - herstellerid: pattern [0-9A-Za-z]{10,24}
    """

    def test_create_valid_credentials(self) -> None:
        """Should create credentials with valid XSD-compliant values."""
        creds = FinanzOnlineCredentials(
            tid="123456789",
            benid="TESTUSER",
            pin="secretpin",
            herstellerid="ATU12345678",
        )
        assert creds.tid == "123456789"
        assert creds.benid == "TESTUSER"
        assert creds.pin == "secretpin"
        assert creds.herstellerid == "ATU12345678"

    def test_immutability(self) -> None:
        """Should be immutable (frozen dataclass)."""
        creds = FinanzOnlineCredentials(
            tid="123456789",
            benid="TESTUSER",
            pin="secretpin",
            herstellerid="ATU12345678",
        )
        with pytest.raises(AttributeError):
            creds.tid = "456"  # type: ignore[misc]

    def test_empty_tid_raises(self) -> None:
        """Should raise ValueError for empty tid."""
        with pytest.raises(ValueError, match="tid.*required"):
            FinanzOnlineCredentials(tid="", benid="TESTUSER", pin="secretpin", herstellerid="ATU12345678")

    def test_tid_too_short_raises(self) -> None:
        """Should raise ValueError for tid shorter than 8 chars."""
        with pytest.raises(ValueError, match="tid must be 8-12 alphanumeric"):
            FinanzOnlineCredentials(tid="1234567", benid="TESTUSER", pin="secretpin", herstellerid="ATU12345678")

    def test_tid_too_long_raises(self) -> None:
        """Should raise ValueError for tid longer than 12 chars."""
        with pytest.raises(ValueError, match="tid must be 8-12 alphanumeric"):
            FinanzOnlineCredentials(tid="1234567890123", benid="TESTUSER", pin="secretpin", herstellerid="ATU12345678")

    def test_empty_benid_raises(self) -> None:
        """Should raise ValueError for empty benid."""
        with pytest.raises(ValueError, match="benid.*required"):
            FinanzOnlineCredentials(tid="123456789", benid="", pin="secretpin", herstellerid="ATU12345678")

    def test_benid_too_short_raises(self) -> None:
        """Should raise ValueError for benid shorter than 5 chars."""
        with pytest.raises(ValueError, match="benid must be 5-12 characters"):
            FinanzOnlineCredentials(tid="123456789", benid="ABCD", pin="secretpin", herstellerid="ATU12345678")

    def test_empty_pin_raises(self) -> None:
        """Should raise ValueError for empty pin."""
        with pytest.raises(ValueError, match="pin.*required"):
            FinanzOnlineCredentials(tid="123456789", benid="TESTUSER", pin="", herstellerid="ATU12345678")

    def test_pin_too_short_raises(self) -> None:
        """Should raise ValueError for pin shorter than 5 chars."""
        with pytest.raises(ValueError, match="pin must be 5-128 characters"):
            FinanzOnlineCredentials(tid="123456789", benid="TESTUSER", pin="1234", herstellerid="ATU12345678")

    def test_empty_herstellerid_raises(self) -> None:
        """Should raise ValueError for empty herstellerid."""
        with pytest.raises(ValueError, match="herstellerid.*required"):
            FinanzOnlineCredentials(tid="123456789", benid="TESTUSER", pin="secretpin", herstellerid="")

    def test_herstellerid_too_short_raises(self) -> None:
        """Should raise ValueError for herstellerid shorter than 10 chars."""
        with pytest.raises(ValueError, match="herstellerid must be 10-24 alphanumeric"):
            FinanzOnlineCredentials(tid="123456789", benid="TESTUSER", pin="secretpin", herstellerid="ATU123456")


class TestSessionInfo:
    """Tests for SessionInfo dataclass."""

    def test_create_valid_session(self) -> None:
        """Should create session info with valid values."""
        session = SessionInfo(session_id="ABC123", return_code=0, message="OK")
        assert session.session_id == "ABC123"
        assert session.return_code == 0
        assert session.message == "OK"

    def test_is_valid_success(self) -> None:
        """Should return True for successful session."""
        session = SessionInfo(session_id="ABC123", return_code=0, message="OK")
        assert session.is_valid is True

    def test_is_valid_failure_code(self) -> None:
        """Should return False for non-zero return code."""
        session = SessionInfo(session_id="ABC123", return_code=-1, message="Error")
        assert session.is_valid is False

    def test_is_valid_empty_session_id(self) -> None:
        """Should return False for empty session ID even with code 0."""
        session = SessionInfo(session_id="", return_code=0, message="OK")
        assert session.is_valid is False


class TestUidCheckRequest:
    """Tests for UidCheckRequest dataclass."""

    def test_create_valid_request(self) -> None:
        """Should create request with valid Austrian UID."""
        request = UidCheckRequest(uid_tn="ATU12345678", uid="DE123456789")
        assert request.uid_tn == "ATU12345678"
        assert request.uid == "DE123456789"
        assert request.stufe == 2

    def test_uid_tn_case_insensitive(self) -> None:
        """Should accept lowercase ATU prefix."""
        request = UidCheckRequest(uid_tn="atu12345678", uid="DE123456789")
        assert request.uid_tn == "atu12345678"

    def test_empty_uid_tn_raises(self) -> None:
        """Should raise ValueError for empty uid_tn."""
        with pytest.raises(ValueError, match="uid_tn.*required"):
            UidCheckRequest(uid_tn="", uid="DE123456789")

    def test_uid_tn_not_starting_atu_raises(self) -> None:
        """Should raise ValueError if uid_tn doesn't start with ATU."""
        with pytest.raises(ValueError, match="start with 'ATU'"):
            UidCheckRequest(uid_tn="DE123456789", uid="FR123456789")

    def test_empty_uid_raises(self) -> None:
        """Should raise ValueError for empty target uid."""
        with pytest.raises(ValueError, match="uid.*required"):
            UidCheckRequest(uid_tn="ATU12345678", uid="")

    def test_stufe_must_be_2(self) -> None:
        """Should raise ValueError for stufe != 2."""
        with pytest.raises(ValueError, match="Level 2"):
            UidCheckRequest(uid_tn="ATU12345678", uid="DE123456789", stufe=1)


class TestAddress:
    """Tests for Address dataclass."""

    def test_create_empty_address(self) -> None:
        """Should create address with default empty lines."""
        addr = Address()
        assert addr.line1 == ""
        assert addr.is_empty is True

    def test_create_full_address(self) -> None:
        """Should create address with all lines."""
        addr = Address(
            line1="Company GmbH",
            line2="Street 1",
            line3="1010 Vienna",
            line4="Austria",
            line5="",
            line6="",
        )
        assert addr.line1 == "Company GmbH"
        assert addr.line4 == "Austria"

    def test_as_lines_filters_empty(self) -> None:
        """Should return only non-empty lines."""
        addr = Address(line1="Name", line3="City")
        lines = addr.as_lines()
        assert lines == ["Name", "City"]

    def test_as_text_default_separator(self) -> None:
        """Should join lines with newline by default."""
        addr = Address(line1="Name", line2="Street")
        assert addr.as_text() == "Name\nStreet"

    def test_as_text_custom_separator(self) -> None:
        """Should use custom separator."""
        addr = Address(line1="Name", line2="Street")
        assert addr.as_text(separator=", ") == "Name, Street"

    def test_is_empty_true(self) -> None:
        """Should return True for address with no content."""
        assert Address().is_empty is True
        assert Address(line1="", line2="").is_empty is True

    def test_is_empty_false(self) -> None:
        """Should return False for address with content."""
        assert Address(line1="Name").is_empty is False


class TestUidCheckResult:
    """Tests for UidCheckResult dataclass."""

    def test_create_valid_result(self) -> None:
        """Should create result with company info."""
        addr = Address(line1="Test GmbH", line2="Vienna")
        result = UidCheckResult(
            uid="DE123456789",
            return_code=0,
            message="UID is valid",
            name="Test Company",
            address=addr,
        )
        assert result.uid == "DE123456789"
        assert result.return_code == 0
        assert result.is_valid is True
        assert result.name == "Test Company"
        assert result.address == addr

    def test_is_valid_true(self) -> None:
        """Should return True for return_code 0."""
        result = UidCheckResult(uid="DE123", return_code=0, message="OK")
        assert result.is_valid is True

    def test_is_valid_false(self) -> None:
        """Should return False for non-zero return_code."""
        result = UidCheckResult(uid="DE123", return_code=1, message="Invalid")
        assert result.is_valid is False

    def test_is_invalid_true(self) -> None:
        """Should return True for return_code 1."""
        result = UidCheckResult(uid="DE123", return_code=1, message="Invalid")
        assert result.is_invalid is True

    def test_is_invalid_false(self) -> None:
        """Should return False for return_codes other than 1."""
        assert UidCheckResult(uid="DE", return_code=0, message="").is_invalid is False
        assert UidCheckResult(uid="DE", return_code=-1, message="").is_invalid is False

    def test_has_company_info_with_name(self) -> None:
        """Should return True when name is present."""
        result = UidCheckResult(uid="DE123", return_code=0, message="OK", name="Company")
        assert result.has_company_info is True

    def test_has_company_info_with_address(self) -> None:
        """Should return True when address has content."""
        addr = Address(line1="Address")
        result = UidCheckResult(uid="DE123", return_code=0, message="OK", address=addr)
        assert result.has_company_info is True

    def test_has_company_info_false(self) -> None:
        """Should return False when no company info."""
        result = UidCheckResult(uid="DE123", return_code=1, message="Invalid")
        assert result.has_company_info is False

    def test_timestamp_default(self) -> None:
        """Should have timestamp set to approximately now."""
        before = datetime.now(timezone.utc)
        result = UidCheckResult(uid="DE123", return_code=0, message="OK")
        after = datetime.now(timezone.utc)
        assert before <= result.timestamp <= after

    def test_timestamp_custom(self) -> None:
        """Should accept custom timestamp."""
        ts = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = UidCheckResult(uid="DE123", return_code=0, message="OK", timestamp=ts)
        assert result.timestamp == ts
