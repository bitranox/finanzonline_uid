"""Tests for email notification adapter.

Tests cover email formatting and sending with mocked SMTP.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from uid_check_austria.adapters.notification.email_adapter import (
    EmailNotificationAdapter,
    format_error_html,
    format_error_plain,
    format_result_html,
    format_result_plain,
)
from uid_check_austria.domain.models import Address, UidCheckResult
from uid_check_austria.enums import EmailFormat
from uid_check_austria.mail import EmailConfig


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
def email_config() -> EmailConfig:
    """Email configuration fixture."""
    return EmailConfig(
        smtp_hosts=["smtp.example.com:587"],
        from_address="test@example.com",
    )


@pytest.fixture
def result_with_address_only() -> UidCheckResult:
    """Result with address but no name."""
    return UidCheckResult(
        uid="DE123456789",
        return_code=0,
        message="UID is valid",
        name="",
        address=Address(line1="Street 1", line2="12345 City"),
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


class TestFormatResultPlain:
    """Tests for format_result_plain function."""

    def test_contains_uid(self, valid_result: UidCheckResult) -> None:
        """Should include UID in output."""
        output = format_result_plain(valid_result)
        assert "DE123456789" in output

    def test_contains_stufe_2_in_header(self, valid_result: UidCheckResult) -> None:
        """Should include Stufe 2 in header."""
        output = format_result_plain(valid_result)
        assert "Stufe 2" in output

    def test_contains_query_level_line(self, valid_result: UidCheckResult) -> None:
        """Should include Query Level line with Stufe 2."""
        output = format_result_plain(valid_result)
        assert "Query Level: Stufe 2" in output

    def test_contains_status(self, valid_result: UidCheckResult) -> None:
        """Should include status."""
        output = format_result_plain(valid_result)
        assert "VALID" in output

    def test_contains_company_info(self, valid_result: UidCheckResult) -> None:
        """Should include company info."""
        output = format_result_plain(valid_result)
        assert "Test Company GmbH" in output
        assert "Street 1" in output

    def test_contains_address_without_name(self, result_with_address_only: UidCheckResult) -> None:
        """Should show address even when name is not available."""
        output = format_result_plain(result_with_address_only)
        assert "Company Information" in output
        assert "Street 1" in output
        assert "12345 City" in output

    def test_invalid_no_company(self, invalid_result: UidCheckResult) -> None:
        """Should not include company info for invalid results."""
        output = format_result_plain(invalid_result)
        assert "Company Information" not in output

    def test_contains_timestamp(self, valid_result: UidCheckResult) -> None:
        """Should include timestamp in local time format."""
        output = format_result_plain(valid_result)
        # Verify timestamp is present (exact time varies by timezone)
        assert "Timestamp:" in output
        # Check date portion is present and UTC suffix is NOT present (now local time)
        assert "UTC" not in output


class TestFormatResultHtml:
    """Tests for format_result_html function."""

    def test_valid_html_structure(self, valid_result: UidCheckResult) -> None:
        """Should produce valid HTML structure."""
        output = format_result_html(valid_result)
        assert "<!DOCTYPE html>" in output
        assert "<html>" in output
        assert "</html>" in output

    def test_contains_stufe_2_in_title(self, valid_result: UidCheckResult) -> None:
        """Should include Stufe 2 in HTML title."""
        output = format_result_html(valid_result)
        assert "Stufe 2" in output

    def test_contains_query_level_row(self, valid_result: UidCheckResult) -> None:
        """Should include Query Level row with Stufe 2."""
        output = format_result_html(valid_result)
        assert "Query Level:" in output
        assert "Stufe 2" in output

    def test_contains_uid(self, valid_result: UidCheckResult) -> None:
        """Should include UID."""
        output = format_result_html(valid_result)
        assert "DE123456789" in output

    def test_contains_status_badge(self, valid_result: UidCheckResult) -> None:
        """Should include status badge."""
        output = format_result_html(valid_result)
        assert "VALID" in output
        assert "#28a745" in output  # Green color for valid

    def test_invalid_status_badge(self, invalid_result: UidCheckResult) -> None:
        """Should show red badge for invalid."""
        output = format_result_html(invalid_result)
        assert "INVALID" in output
        assert "#dc3545" in output  # Red color for invalid

    def test_contains_company_info(self, valid_result: UidCheckResult) -> None:
        """Should include company info."""
        output = format_result_html(valid_result)
        assert "Test Company GmbH" in output

    def test_contains_address_without_name(self, result_with_address_only: UidCheckResult) -> None:
        """Should show address even when name is not available."""
        output = format_result_html(result_with_address_only)
        assert "Company Information" in output
        assert "Street 1" in output
        assert "12345 City" in output


class TestEmailNotificationAdapter:
    """Tests for EmailNotificationAdapter."""

    def test_send_result_success(
        self,
        valid_result: UidCheckResult,
        email_config: EmailConfig,
    ) -> None:
        """Should send email successfully."""
        adapter = EmailNotificationAdapter(email_config)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            mock_send.return_value = True

            result = adapter.send_result(valid_result, ["recipient@example.com"])

            assert result is True
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args.kwargs
            assert call_kwargs["recipients"] == ["recipient@example.com"]
            assert "DE123456789" in call_kwargs["subject"]
            assert "VALID" in call_kwargs["subject"]

    def test_send_result_invalid_uid(
        self,
        invalid_result: UidCheckResult,
        email_config: EmailConfig,
    ) -> None:
        """Should include INVALID in subject for invalid UIDs."""
        adapter = EmailNotificationAdapter(email_config)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            mock_send.return_value = True

            adapter.send_result(invalid_result, ["recipient@example.com"])

            call_kwargs = mock_send.call_args.kwargs
            assert "INVALID" in call_kwargs["subject"]

    def test_send_result_no_recipients(
        self,
        valid_result: UidCheckResult,
        email_config: EmailConfig,
    ) -> None:
        """Should return False when no recipients."""
        adapter = EmailNotificationAdapter(email_config)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            result = adapter.send_result(valid_result, [])

            assert result is False
            mock_send.assert_not_called()

    def test_send_result_failure(
        self,
        valid_result: UidCheckResult,
        email_config: EmailConfig,
    ) -> None:
        """Should return False on send failure."""
        adapter = EmailNotificationAdapter(email_config)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            mock_send.side_effect = RuntimeError("SMTP error")

            result = adapter.send_result(valid_result, ["recipient@example.com"])

            assert result is False

    def test_send_result_includes_html(
        self,
        valid_result: UidCheckResult,
        email_config: EmailConfig,
    ) -> None:
        """Should include HTML body."""
        adapter = EmailNotificationAdapter(email_config)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            mock_send.return_value = True

            adapter.send_result(valid_result, ["recipient@example.com"])

            call_kwargs = mock_send.call_args.kwargs
            assert "body_html" in call_kwargs
            assert "<!DOCTYPE html>" in call_kwargs["body_html"]


class TestFormatErrorPlain:
    """Tests for format_error_plain function."""

    def test_contains_uid(self) -> None:
        """Should include UID in output."""
        output = format_error_plain(
            error_type="Test Error",
            error_message="Test message",
            uid="DE123456789",
        )
        assert "DE123456789" in output

    def test_contains_error_type(self) -> None:
        """Should include error type."""
        output = format_error_plain(
            error_type="Authentication Error",
            error_message="Test message",
            uid="DE123456789",
        )
        assert "Authentication Error" in output

    def test_contains_error_status(self) -> None:
        """Should include ERROR status."""
        output = format_error_plain(
            error_type="Test Error",
            error_message="Test message",
            uid="DE123456789",
        )
        assert "ERROR" in output

    def test_contains_return_code_when_provided(self) -> None:
        """Should include return code info when provided."""
        output = format_error_plain(
            error_type="Test Error",
            error_message="Test message",
            uid="DE123456789",
            return_code=-4,
        )
        assert "-4" in output
        assert "Return Code" in output

    def test_contains_retryable_info(self) -> None:
        """Should include retryable status."""
        output = format_error_plain(
            error_type="Test Error",
            error_message="Test message",
            uid="DE123456789",
            retryable=True,
        )
        assert "Retryable:" in output
        assert "Yes" in output


class TestFormatErrorHtml:
    """Tests for format_error_html function."""

    def test_valid_html_structure(self) -> None:
        """Should produce valid HTML structure."""
        output = format_error_html(
            error_type="Test Error",
            error_message="Test message",
            uid="DE123456789",
        )
        assert "<!DOCTYPE html>" in output
        assert "<html>" in output
        assert "</html>" in output

    def test_contains_uid(self) -> None:
        """Should include UID."""
        output = format_error_html(
            error_type="Test Error",
            error_message="Test message",
            uid="DE123456789",
        )
        assert "DE123456789" in output

    def test_contains_error_badge(self) -> None:
        """Should include error badge."""
        output = format_error_html(
            error_type="Test Error",
            error_message="Test message",
            uid="DE123456789",
        )
        assert "ERROR" in output
        assert "#dc3545" in output  # Red color for error

    def test_contains_return_code_section(self) -> None:
        """Should include return code section when provided."""
        output = format_error_html(
            error_type="Test Error",
            error_message="Test message",
            uid="DE123456789",
            return_code=-1,
        )
        assert "-1" in output


class TestSendError:
    """Tests for EmailNotificationAdapter.send_error method."""

    def test_send_error_success(self, email_config: EmailConfig) -> None:
        """Should send error email successfully."""
        adapter = EmailNotificationAdapter(email_config)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            mock_send.return_value = True

            result = adapter.send_error(
                error_type="Session Error",
                error_message="Connection failed",
                uid="DE123456789",
                recipients=["admin@example.com"],
            )

            assert result is True
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args.kwargs
            assert call_kwargs["recipients"] == ["admin@example.com"]
            assert "ERROR" in call_kwargs["subject"]
            assert "DE123456789" in call_kwargs["subject"]
            assert "Session Error" in call_kwargs["subject"]

    def test_send_error_no_recipients(self, email_config: EmailConfig) -> None:
        """Should return False when no recipients."""
        adapter = EmailNotificationAdapter(email_config)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            result = adapter.send_error(
                error_type="Test Error",
                error_message="Test",
                uid="DE123456789",
                recipients=[],
            )

            assert result is False
            mock_send.assert_not_called()

    def test_send_error_failure(self, email_config: EmailConfig) -> None:
        """Should return False on send failure."""
        adapter = EmailNotificationAdapter(email_config)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            mock_send.side_effect = RuntimeError("SMTP error")

            result = adapter.send_error(
                error_type="Test Error",
                error_message="Test",
                uid="DE123456789",
                recipients=["admin@example.com"],
            )

            assert result is False

    def test_send_error_includes_return_code(self, email_config: EmailConfig) -> None:
        """Should include return code in email."""
        adapter = EmailNotificationAdapter(email_config)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            mock_send.return_value = True

            adapter.send_error(
                error_type="Auth Error",
                error_message="Not authorized",
                uid="DE123456789",
                recipients=["admin@example.com"],
                return_code=-4,
            )

            call_kwargs = mock_send.call_args.kwargs
            assert "-4" in call_kwargs["body"]

    def test_send_error_includes_retryable(self, email_config: EmailConfig) -> None:
        """Should include retryable info in email."""
        adapter = EmailNotificationAdapter(email_config)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            mock_send.return_value = True

            adapter.send_error(
                error_type="Connection Error",
                error_message="Timeout",
                uid="DE123456789",
                recipients=["admin@example.com"],
                retryable=True,
            )

            call_kwargs = mock_send.call_args.kwargs
            assert "Yes" in call_kwargs["body"]


class TestCachedResultFormatting:
    """Tests for cached result notice in email formatting."""

    @pytest.fixture
    def cached_result(self) -> UidCheckResult:
        """Cached UID check result fixture."""
        return UidCheckResult(
            uid="DE123456789",
            return_code=0,
            message="UID is valid",
            name="Test Company GmbH",
            address=Address(line1="Test Company GmbH", line2="Street 1", line3="12345 City"),
            timestamp=datetime(2025, 1, 20, 14, 0, 0, tzinfo=timezone.utc),
            from_cache=True,
            cached_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        )

    def test_plain_cached_result_contains_notice(self, cached_result: UidCheckResult) -> None:
        """Should include cache notice in plain text output."""
        output = format_result_plain(cached_result)
        assert "CACHED result" in output
        assert "Originally queried:" in output
        # Timestamp is now in local time, verify format is present without UTC suffix
        assert "UTC" not in output.split("Originally queried:")[1].split("\n")[0]

    def test_plain_non_cached_result_no_notice(self, valid_result: UidCheckResult) -> None:
        """Should not include cache notice for non-cached results."""
        output = format_result_plain(valid_result)
        assert "CACHED result" not in output

    def test_html_cached_result_contains_notice(self, cached_result: UidCheckResult) -> None:
        """Should include cache notice in HTML output."""
        output = format_result_html(cached_result)
        assert "Cached Result" in output
        assert "Originally queried:" in output
        # Timestamp is now in local time format without UTC suffix
        assert "UTC" not in output

    def test_html_non_cached_result_no_notice(self, valid_result: UidCheckResult) -> None:
        """Should not include cache notice for non-cached results."""
        output = format_result_html(valid_result)
        assert "Cached Result" not in output

    def test_html_cache_notice_styled(self, cached_result: UidCheckResult) -> None:
        """Should include styled info box for cache notice."""
        output = format_result_html(cached_result)
        # Check for info box styling (Bootstrap-like info colors)
        assert "#d1ecf1" in output  # Info background color
        assert "#0c5460" in output  # Info text color


class TestEmailFormat:
    """Tests for email format configuration."""

    def test_default_format_sends_both(
        self,
        valid_result: UidCheckResult,
        email_config: EmailConfig,
    ) -> None:
        """Should send both formats when using default."""
        adapter = EmailNotificationAdapter(email_config)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            mock_send.return_value = True
            adapter.send_result(valid_result, ["test@example.com"])

            call_kwargs = mock_send.call_args.kwargs
            assert call_kwargs["body"] != ""
            assert call_kwargs["body_html"] != ""

    def test_plain_format_sends_plain_only(self, valid_result: UidCheckResult, email_config: EmailConfig) -> None:
        """Should send only plain text when format is PLAIN."""
        adapter = EmailNotificationAdapter(email_config, email_format=EmailFormat.PLAIN)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            mock_send.return_value = True
            adapter.send_result(valid_result, ["test@example.com"])

            call_kwargs = mock_send.call_args.kwargs
            assert call_kwargs["body"] != ""
            assert call_kwargs["body_html"] == ""

    def test_html_format_sends_html_only(self, valid_result: UidCheckResult, email_config: EmailConfig) -> None:
        """Should send only HTML when format is HTML."""
        adapter = EmailNotificationAdapter(email_config, email_format=EmailFormat.HTML)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            mock_send.return_value = True
            adapter.send_result(valid_result, ["test@example.com"])

            call_kwargs = mock_send.call_args.kwargs
            assert call_kwargs["body"] == ""
            assert call_kwargs["body_html"] != ""

    def test_both_format_sends_both(self, valid_result: UidCheckResult, email_config: EmailConfig) -> None:
        """Should send both formats when format is BOTH."""
        adapter = EmailNotificationAdapter(email_config, email_format=EmailFormat.BOTH)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            mock_send.return_value = True
            adapter.send_result(valid_result, ["test@example.com"])

            call_kwargs = mock_send.call_args.kwargs
            assert call_kwargs["body"] != ""
            assert call_kwargs["body_html"] != ""

    def test_error_plain_format_sends_plain_only(self, email_config: EmailConfig) -> None:
        """Should send only plain text for errors when format is PLAIN."""
        adapter = EmailNotificationAdapter(email_config, email_format=EmailFormat.PLAIN)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            mock_send.return_value = True
            adapter.send_error(
                error_type="Test Error",
                error_message="Test",
                uid="DE123456789",
                recipients=["test@example.com"],
            )

            call_kwargs = mock_send.call_args.kwargs
            assert call_kwargs["body"] != ""
            assert call_kwargs["body_html"] == ""

    def test_error_html_format_sends_html_only(self, email_config: EmailConfig) -> None:
        """Should send only HTML for errors when format is HTML."""
        adapter = EmailNotificationAdapter(email_config, email_format=EmailFormat.HTML)

        with patch("uid_check_austria.adapters.notification.email_adapter.send_email") as mock_send:
            mock_send.return_value = True
            adapter.send_error(
                error_type="Test Error",
                error_message="Test",
                uid="DE123456789",
                recipients=["test@example.com"],
            )

            call_kwargs = mock_send.call_args.kwargs
            assert call_kwargs["body"] == ""
            assert call_kwargs["body_html"] != ""
