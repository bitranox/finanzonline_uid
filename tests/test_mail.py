"""Email functionality stories: every sending scenario a single verse.

Verify that the mail wrapper correctly integrates btx_lib_mail with the
application's configuration system and provides a clean interface for
email operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from uid_check_austria.mail import (
    EmailConfig,
    load_email_config_from_dict,
    send_email,
    send_notification,
)


# ============================================================================
# EmailConfig: Default Values
# ============================================================================


@pytest.mark.os_agnostic
class TestEmailConfigDefaults:
    """EmailConfig provides sensible defaults when created without arguments."""

    def test_smtp_hosts_default_to_empty_list(self) -> None:
        """SMTP hosts start empty until configured."""
        assert EmailConfig().smtp_hosts == []

    def test_from_address_defaults_to_localhost(self) -> None:
        """Default sender is noreply@localhost."""
        assert EmailConfig().from_address == "noreply@localhost"

    def test_smtp_credentials_default_to_none(self) -> None:
        """No credentials are configured by default."""
        config = EmailConfig()
        assert config.smtp_username is None
        assert config.smtp_password is None

    def test_starttls_enabled_by_default(self) -> None:
        """STARTTLS is on by default for security."""
        assert EmailConfig().use_starttls is True

    def test_timeout_defaults_to_thirty_seconds(self) -> None:
        """30 seconds is a reasonable default timeout."""
        assert EmailConfig().timeout == 30.0

    def test_missing_attachments_raise_by_default(self) -> None:
        """Missing attachments cause errors by default."""
        assert EmailConfig().raise_on_missing_attachments is True

    def test_invalid_recipients_raise_by_default(self) -> None:
        """Invalid recipients cause errors by default."""
        assert EmailConfig().raise_on_invalid_recipient is True


# ============================================================================
# EmailConfig: Custom Values
# ============================================================================


@pytest.mark.os_agnostic
class TestEmailConfigCustomValues:
    """EmailConfig accepts and stores custom values correctly."""

    def test_custom_smtp_hosts_are_stored(self) -> None:
        """Custom SMTP hosts are preserved."""
        config = EmailConfig(smtp_hosts=["smtp.example.com:587"])
        assert config.smtp_hosts == ["smtp.example.com:587"]

    def test_custom_from_address_is_stored(self) -> None:
        """Custom sender address is preserved."""
        config = EmailConfig(from_address="test@example.com")
        assert config.from_address == "test@example.com"

    def test_custom_credentials_are_stored(self) -> None:
        """Custom username and password are preserved."""
        config = EmailConfig(smtp_username="user", smtp_password="pass")
        assert config.smtp_username == "user"
        assert config.smtp_password == "pass"

    def test_starttls_can_be_disabled(self) -> None:
        """STARTTLS can be turned off when needed."""
        config = EmailConfig(use_starttls=False)
        assert config.use_starttls is False

    def test_custom_timeout_is_stored(self) -> None:
        """Custom timeout values are preserved."""
        config = EmailConfig(timeout=60.0)
        assert config.timeout == 60.0


# ============================================================================
# EmailConfig: Immutability
# ============================================================================


@pytest.mark.os_agnostic
def test_email_config_is_frozen() -> None:
    """EmailConfig cannot be modified after creation."""
    config = EmailConfig()
    with pytest.raises(AttributeError):
        config.smtp_hosts = ["new.smtp.com"]  # type: ignore[misc]


# ============================================================================
# EmailConfig: Validation
# ============================================================================


@pytest.mark.os_agnostic
class TestEmailConfigValidation:
    """EmailConfig validates its inputs on creation."""

    def test_negative_timeout_is_rejected(self) -> None:
        """Negative timeout values fail validation."""
        with pytest.raises(ValueError, match="timeout must be positive"):
            EmailConfig(timeout=-5.0)

    def test_zero_timeout_is_rejected(self) -> None:
        """Zero timeout is invalid (would cause immediate failures)."""
        with pytest.raises(ValueError, match="timeout must be positive"):
            EmailConfig(timeout=0.0)

    def test_from_address_without_at_is_rejected(self) -> None:
        """From address must contain @ sign."""
        with pytest.raises(ValueError, match="from_address must contain @"):
            EmailConfig(from_address="not-an-email")

    def test_malformed_smtp_host_port_is_rejected(self) -> None:
        """SMTP host with multiple colons is invalid."""
        with pytest.raises(ValueError, match="Invalid SMTP host format"):
            EmailConfig(smtp_hosts=["smtp.test.com:587:extra"])

    def test_non_numeric_port_is_rejected(self) -> None:
        """Port must be a number."""
        with pytest.raises(ValueError, match="Port must be numeric"):
            EmailConfig(smtp_hosts=["smtp.test.com:abc"])

    def test_port_above_65535_is_rejected(self) -> None:
        """Port must be within TCP range."""
        with pytest.raises(ValueError, match="Port must be 1-65535"):
            EmailConfig(smtp_hosts=["smtp.test.com:99999"])

    def test_port_zero_is_rejected(self) -> None:
        """Port 0 is reserved and invalid."""
        with pytest.raises(ValueError, match="Port must be 1-65535"):
            EmailConfig(smtp_hosts=["smtp.test.com:0"])

    def test_host_without_port_is_accepted(self) -> None:
        """SMTP host without explicit port uses default."""
        config = EmailConfig(smtp_hosts=["smtp.test.com"])
        assert config.smtp_hosts == ["smtp.test.com"]

    def test_host_with_valid_port_is_accepted(self) -> None:
        """SMTP host with standard port is valid."""
        config = EmailConfig(smtp_hosts=["smtp.test.com:587"])
        assert config.smtp_hosts == ["smtp.test.com:587"]


# ============================================================================
# EmailConfig: Conversion to ConfMail
# ============================================================================


@pytest.mark.os_agnostic
def test_to_conf_mail_creates_btx_compatible_config() -> None:
    """to_conf_mail produces btx_lib_mail compatible configuration."""
    config = EmailConfig(
        smtp_hosts=["smtp.example.com:587"],
        smtp_username="user",
        smtp_password="pass",
        timeout=45.0,
    )

    conf = config.to_conf_mail()

    assert conf.smtphosts == ["smtp.example.com:587"]
    assert conf.smtp_username == "user"
    assert conf.smtp_password == "pass"
    assert conf.smtp_timeout == 45.0
    assert conf.smtp_use_starttls is True


# ============================================================================
# load_email_config_from_dict: Basic Loading
# ============================================================================


@pytest.mark.os_agnostic
class TestLoadEmailConfigFromDict:
    """Configuration loading from dictionary handles various scenarios."""

    def test_missing_email_section_uses_defaults(self) -> None:
        """Missing email section falls back to defaults."""
        config = load_email_config_from_dict({})
        assert config.smtp_hosts == []
        assert config.from_address == "noreply@localhost"

    def test_extracts_values_from_email_section(self) -> None:
        """Email section values are correctly extracted."""
        config_dict = {
            "email": {
                "smtp_hosts": ["smtp.test.com:587"],
                "from_address": "alerts@test.com",
                "smtp_username": "testuser",
                "smtp_password": "testpass",
                "use_starttls": False,
                "timeout": 120.0,
            }
        }

        config = load_email_config_from_dict(config_dict)

        assert config.smtp_hosts == ["smtp.test.com:587"]
        assert config.from_address == "alerts@test.com"
        assert config.smtp_username == "testuser"
        assert config.smtp_password == "testpass"
        assert config.use_starttls is False
        assert config.timeout == 120.0

    def test_partial_config_inherits_defaults(self) -> None:
        """Partial config merges with defaults for missing values."""
        config_dict = {
            "email": {
                "smtp_hosts": ["smtp.partial.com"],
                "from_address": "partial@test.com",
            }
        }

        config = load_email_config_from_dict(config_dict)

        assert config.smtp_hosts == ["smtp.partial.com"]
        assert config.from_address == "partial@test.com"
        assert config.smtp_username is None
        assert config.use_starttls is True


# ============================================================================
# load_email_config_from_dict: Type Coercion
# ============================================================================


@pytest.mark.os_agnostic
class TestLoadEmailConfigTypeCoercion:
    """Configuration loading handles type mismatches gracefully."""

    def test_non_dict_email_section_uses_defaults(self) -> None:
        """Non-dict email section falls back to defaults."""
        config = load_email_config_from_dict({"email": "invalid"})
        assert config.smtp_hosts == []
        assert config.from_address == "noreply@localhost"

    def test_invalid_timeout_uses_default(self) -> None:
        """String timeout falls back to default."""
        config = load_email_config_from_dict({"email": {"timeout": "not_a_number"}})
        assert config.timeout == 30.0

    def test_non_list_smtp_hosts_uses_empty_list(self) -> None:
        """String smtp_hosts falls back to empty list."""
        config = load_email_config_from_dict({"email": {"smtp_hosts": "should_be_list"}})
        assert config.smtp_hosts == []

    def test_string_boolean_uses_default(self) -> None:
        """String boolean value falls back to default."""
        config = load_email_config_from_dict({"email": {"use_starttls": "yes"}})
        assert config.use_starttls is True

    def test_empty_string_username_is_preserved(self) -> None:
        """Empty string username is preserved (current behavior)."""
        config = load_email_config_from_dict({"email": {"smtp_username": ""}})
        assert config.smtp_username == ""

    def test_mixed_valid_invalid_values(self) -> None:
        """Valid values are used; invalid ones fall back to defaults."""
        config_dict = {
            "email": {
                "smtp_hosts": ["smtp.test.com:587"],
                "from_address": "test@example.com",
                "timeout": "invalid",
                "use_starttls": "maybe",
            }
        }

        config = load_email_config_from_dict(config_dict)

        assert config.smtp_hosts == ["smtp.test.com:587"]
        assert config.from_address == "test@example.com"
        assert config.timeout == 30.0
        assert config.use_starttls is True


# ============================================================================
# send_email: Success Scenarios
# ============================================================================


@pytest.mark.os_agnostic
class TestSendEmailSuccess:
    """Email sending succeeds under normal conditions."""

    def test_simple_message_is_delivered(self, valid_email_config: Any) -> None:
        """Basic email with required fields is sent."""
        with patch("smtplib.SMTP"):
            result = send_email(
                config=valid_email_config,
                recipients="recipient@test.com",
                subject="Test Subject",
                body="Test body",
            )
        assert result is True

    def test_html_body_is_included(self, valid_email_config: Any) -> None:
        """Email with HTML body is sent as multipart."""
        with patch("smtplib.SMTP"):
            result = send_email(
                config=valid_email_config,
                recipients="recipient@test.com",
                subject="Test Subject",
                body="Plain text",
                body_html="<h1>HTML</h1>",
            )
        assert result is True

    def test_multiple_recipients_are_accepted(self, valid_email_config: Any) -> None:
        """Email can be sent to multiple recipients."""
        with patch("smtplib.SMTP"):
            result = send_email(
                config=valid_email_config,
                recipients=["user1@test.com", "user2@test.com"],
                subject="Test Subject",
                body="Test body",
            )
        assert result is True

    def test_sender_override_is_applied(self, valid_email_config: Any) -> None:
        """from_address parameter overrides config default."""
        with patch("smtplib.SMTP"):
            result = send_email(
                config=valid_email_config,
                recipients="recipient@test.com",
                subject="Test Subject",
                body="Test body",
                from_address="override@test.com",
            )
        assert result is True

    def test_attachments_are_included(
        self,
        valid_email_config: Any,
        tmp_path: Path,
    ) -> None:
        """Email with file attachments is sent."""
        attachment = tmp_path / "test.txt"
        attachment.write_text("Test attachment content")

        with patch("smtplib.SMTP"):
            result = send_email(
                config=valid_email_config,
                recipients="recipient@test.com",
                subject="Test Subject",
                body="Test body",
                attachments=[attachment],
            )
        assert result is True

    def test_credentials_are_used(self) -> None:
        """SMTP credentials are used when configured."""
        config = EmailConfig(
            smtp_hosts=["smtp.test.com:587"],
            from_address="sender@test.com",
            smtp_username="testuser",
            smtp_password="testpass",
        )

        with patch("smtplib.SMTP"):
            result = send_email(
                config=config,
                recipients="recipient@test.com",
                subject="Test Subject",
                body="Test body",
            )
        assert result is True


# ============================================================================
# send_notification: Success Scenarios
# ============================================================================


@pytest.mark.os_agnostic
class TestSendNotificationSuccess:
    """Notification sending works for simple text messages."""

    def test_plain_text_is_delivered(self, valid_email_config: Any) -> None:
        """Notification sends plain-text email."""
        with patch("smtplib.SMTP"):
            result = send_notification(
                config=valid_email_config,
                recipients="admin@test.com",
                subject="Alert",
                message="System notification",
            )
        assert result is True

    def test_multiple_recipients_are_accepted(self, valid_email_config: Any) -> None:
        """Notification can be sent to multiple recipients."""
        with patch("smtplib.SMTP"):
            result = send_notification(
                config=valid_email_config,
                recipients=["admin1@test.com", "admin2@test.com"],
                subject="Alert",
                message="System notification",
            )
        assert result is True


# ============================================================================
# send_email: Error Scenarios
# ============================================================================


@pytest.mark.os_agnostic
class TestSendEmailErrors:
    """Email sending fails gracefully with appropriate errors."""

    def test_smtp_connection_failure_raises(self, valid_email_config: Any) -> None:
        """SMTP connection failure raises RuntimeError."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = ConnectionError("Cannot connect to SMTP server")

            with pytest.raises(RuntimeError, match="failed.*on all of following hosts"):
                send_email(
                    config=valid_email_config,
                    recipients="recipient@test.com",
                    subject="Test",
                    body="Hello",
                )

    def test_authentication_failure_raises(self) -> None:
        """SMTP authentication failure raises RuntimeError."""
        mock_instance = MagicMock()
        mock_instance.login.side_effect = Exception("Authentication failed")

        config = EmailConfig(
            smtp_hosts=["smtp.test.com:587"],
            from_address="sender@test.com",
            smtp_username="user@test.com",
            smtp_password="wrong_password",
        )

        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__.return_value = mock_instance

            with pytest.raises(RuntimeError, match="failed.*on all of following hosts"):
                send_email(
                    config=config,
                    recipients="recipient@test.com",
                    subject="Test",
                    body="Hello",
                )

    def test_recipient_validation_failure_raises(self, valid_email_config: Any) -> None:
        """Invalid recipient raises RuntimeError."""
        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = ValueError("Invalid recipient address")

            with pytest.raises(RuntimeError, match="following recipients failed"):
                send_email(
                    config=valid_email_config,
                    recipients="recipient@test.com",
                    subject="Test",
                    body="Hello",
                )

    def test_missing_attachment_raises(self, tmp_path: Path) -> None:
        """Missing attachment raises FileNotFoundError when configured."""
        nonexistent = tmp_path / "nonexistent.txt"

        config = EmailConfig(
            smtp_hosts=["smtp.test.com:587"],
            from_address="sender@test.com",
            raise_on_missing_attachments=True,
        )

        with patch("smtplib.SMTP"):
            with pytest.raises(FileNotFoundError):
                send_email(
                    config=config,
                    recipients="recipient@test.com",
                    subject="Test",
                    body="Hello",
                    attachments=[nonexistent],
                )

    def test_all_smtp_hosts_failing_raises(self) -> None:
        """All SMTP hosts failing raises RuntimeError."""
        config = EmailConfig(
            smtp_hosts=["smtp1.test.com:587", "smtp2.test.com:587"],
            from_address="sender@test.com",
        )

        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = ConnectionError("Connection refused")

            with pytest.raises(RuntimeError, match="following recipients failed"):
                send_email(
                    config=config,
                    recipients="recipient@test.com",
                    subject="Test",
                    body="Hello",
                )


# ============================================================================
# Real SMTP Integration Tests
# ============================================================================


@pytest.mark.os_agnostic
class TestRealSmtpIntegration:
    """Integration tests with real SMTP server (when configured)."""

    def test_real_smtp_sends_email(self, smtp_config_from_env: Any) -> None:
        """Send real email via configured SMTP server."""
        result = send_email(
            config=smtp_config_from_env,
            recipients=smtp_config_from_env.from_address,
            subject="Test Email from uid_check_austria",
            body="Integration test email.\n\nEmail functionality is working.",
        )
        assert result is True

    def test_real_smtp_sends_html_email(self, smtp_config_from_env: Any) -> None:
        """Send HTML email via configured SMTP server."""
        result = send_email(
            config=smtp_config_from_env,
            recipients=smtp_config_from_env.from_address,
            subject="Test HTML Email from uid_check_austria",
            body="This is the plain text version.",
            body_html="<html><body><h1>Test</h1><p><strong>HTML</strong> email.</p></body></html>",
        )
        assert result is True

    def test_real_smtp_sends_notification(self, smtp_config_from_env: Any) -> None:
        """Send notification via configured SMTP server."""
        result = send_notification(
            config=smtp_config_from_env,
            recipients=smtp_config_from_env.from_address,
            subject="Test Notification from uid_check_austria",
            message="This is a test notification.\n\nAll tests passing!",
        )
        assert result is True
