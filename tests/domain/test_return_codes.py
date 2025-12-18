"""Tests for return code definitions.

Tests cover all known return codes, severity mappings, and
handling of unknown codes.
"""

from __future__ import annotations

import pytest

from uid_check_austria.domain.return_codes import (
    ReturnCode,
    ReturnCodeInfo,
    Severity,
    get_return_code_info,
    is_retryable,
    is_success,
)


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_values(self) -> None:
        """Should have expected severity levels."""
        assert Severity.SUCCESS.value == "success"
        assert Severity.WARNING.value == "warning"
        assert Severity.ERROR.value == "error"
        assert Severity.CRITICAL.value == "critical"


class TestReturnCode:
    """Tests for ReturnCode enum."""

    def test_success_code(self) -> None:
        """Should have UID_VALID as 0."""
        assert ReturnCode.UID_VALID.value == 0

    def test_invalid_code(self) -> None:
        """Should have UID_INVALID as 1."""
        assert ReturnCode.UID_INVALID.value == 1

    def test_session_errors(self) -> None:
        """Should have negative session error codes."""
        assert ReturnCode.SESSION_INVALID.value == -1
        assert ReturnCode.SYSTEM_MAINTENANCE.value == -2
        assert ReturnCode.TECHNICAL_ERROR.value == -3
        assert ReturnCode.NOT_AUTHORIZED.value == -4

    def test_rate_limit_codes(self) -> None:
        """Should have rate limit codes in 1500s."""
        assert ReturnCode.RATE_LIMIT_UID_EXCEEDED.value == 1513
        assert ReturnCode.RATE_LIMIT_REQUESTER_EXCEEDED.value == 1514


class TestReturnCodeInfo:
    """Tests for ReturnCodeInfo dataclass."""

    def test_create_info(self) -> None:
        """Should create return code info."""
        info = ReturnCodeInfo(code=0, meaning="Valid", severity=Severity.SUCCESS)
        assert info.code == 0
        assert info.meaning == "Valid"
        assert info.severity == Severity.SUCCESS
        assert info.retryable is False

    def test_retryable_default(self) -> None:
        """Should default retryable to False."""
        info = ReturnCodeInfo(code=1, meaning="Test", severity=Severity.ERROR)
        assert info.retryable is False

    def test_retryable_explicit(self) -> None:
        """Should accept explicit retryable."""
        info = ReturnCodeInfo(code=1, meaning="Test", severity=Severity.ERROR, retryable=True)
        assert info.retryable is True


class TestGetReturnCodeInfo:
    """Tests for get_return_code_info function."""

    def test_valid_uid(self) -> None:
        """Should return success info for code 0."""
        info = get_return_code_info(0)
        assert info.code == 0
        assert info.meaning == "UID is valid"
        assert info.severity == Severity.SUCCESS
        assert info.retryable is False

    def test_invalid_uid(self) -> None:
        """Should return warning info for code 1."""
        info = get_return_code_info(1)
        assert info.code == 1
        assert info.meaning == "UID is invalid"
        assert info.severity == Severity.WARNING

    def test_session_invalid(self) -> None:
        """Should return error for session invalid."""
        info = get_return_code_info(-1)
        assert info.severity == Severity.ERROR
        assert "Session" in info.meaning or "session" in info.meaning

    def test_system_maintenance_retryable(self) -> None:
        """Should mark system maintenance as retryable."""
        info = get_return_code_info(-2)
        assert info.retryable is True
        assert "maintenance" in info.meaning.lower()

    def test_not_authorized_critical(self) -> None:
        """Should mark not authorized as critical."""
        info = get_return_code_info(-4)
        assert info.severity == Severity.CRITICAL

    def test_rate_limit_uid_exceeded(self) -> None:
        """Should return retryable warning for code 1513."""
        info = get_return_code_info(1513)
        assert info.code == 1513
        assert info.severity == Severity.WARNING
        assert info.retryable is True
        assert "rate" in info.meaning.lower() or "limit" in info.meaning.lower()

    def test_service_unavailable_critical(self) -> None:
        """Should mark service unavailable as critical and retryable."""
        info = get_return_code_info(1511)
        assert info.severity == Severity.CRITICAL
        assert info.retryable is True

    def test_unknown_code(self) -> None:
        """Should return generic error for unknown codes."""
        info = get_return_code_info(9999)
        assert info.code == 9999
        assert "Unknown" in info.meaning or "unknown" in info.meaning
        assert info.severity == Severity.ERROR
        assert info.retryable is False

    @pytest.mark.parametrize(
        ("code", "expected_severity"),
        [
            (0, Severity.SUCCESS),
            (1, Severity.WARNING),
            (-1, Severity.ERROR),
            (-4, Severity.CRITICAL),
            (4, Severity.ERROR),
            (10, Severity.WARNING),
            (1511, Severity.CRITICAL),
            (1513, Severity.WARNING),
        ],
    )
    def test_severity_mappings(self, code: int, expected_severity: Severity) -> None:
        """Should map codes to correct severity."""
        info = get_return_code_info(code)
        assert info.severity == expected_severity

    @pytest.mark.parametrize(
        ("code", "expected_retryable"),
        [
            (0, False),
            (1, False),
            (-2, True),
            (-3, True),
            (4, False),
            (12, True),
            (1511, True),
            (1512, True),
            (1513, True),
            (1514, True),
        ],
    )
    def test_retryable_mappings(self, code: int, expected_retryable: bool) -> None:
        """Should map codes to correct retryable status."""
        info = get_return_code_info(code)
        assert info.retryable == expected_retryable


class TestIsSuccess:
    """Tests for is_success function."""

    def test_success_true(self) -> None:
        """Should return True for code 0."""
        assert is_success(0) is True

    def test_success_false(self) -> None:
        """Should return False for non-zero codes."""
        assert is_success(1) is False
        assert is_success(-1) is False
        assert is_success(1513) is False


class TestIsRetryable:
    """Tests for is_retryable function."""

    def test_retryable_true(self) -> None:
        """Should return True for retryable codes."""
        assert is_retryable(-2) is True  # System maintenance
        assert is_retryable(1513) is True  # Rate limit

    def test_retryable_false(self) -> None:
        """Should return False for non-retryable codes."""
        assert is_retryable(0) is False
        assert is_retryable(1) is False
        assert is_retryable(4) is False
