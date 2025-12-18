"""Email sending adapter using btx_lib_mail.

Provides a clean wrapper around btx_lib_mail that integrates with the
application's configuration system and logging infrastructure. Isolates
email functionality behind a domain-appropriate interface.

Contents:
    * :class:`EmailConfig` – Configuration container for email settings
    * :func:`send_email` – Primary email sending interface
    * :func:`send_notification` – Convenience wrapper for simple notifications

System Role:
    Acts as the email adapter layer, bridging btx_lib_mail with the application's
    configuration and logging systems while keeping domain logic decoupled from
    email mechanics.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence, cast

from btx_lib_mail.lib_mail import ConfMail, send as btx_send

logger = logging.getLogger(__name__)


def _default_smtp_hosts() -> list[str]:
    """Factory function for default SMTP hosts list."""
    return []


def _validate_smtp_host(host: str) -> None:
    """Validate a single SMTP host string format.

    Args:
        host: SMTP host in 'hostname' or 'hostname:port' format.

    Raises:
        ValueError: When host format is invalid or port is out of range.
    """
    if ":" not in host:
        return

    parts = host.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid SMTP host format (expected 'host:port'): {host!r}")

    _validate_smtp_port(parts[1], host)


def _validate_smtp_port(port_str: str, host: str) -> None:
    """Validate SMTP port is numeric and in valid range.

    Args:
        port_str: Port string to validate.
        host: Full host string for error messages.

    Raises:
        ValueError: When port is non-numeric or out of range.
    """
    try:
        port = int(port_str)
    except ValueError as e:
        raise ValueError(f"Port must be numeric in {host!r}") from e

    if not (1 <= port <= 65535):
        raise ValueError(f"Port must be 1-65535 in {host!r}")


@dataclass(frozen=True, slots=True)
class EmailConfig:
    """Email configuration container.

    Provides a domain-appropriate configuration object that maps cleanly
    to lib_layered_config while remaining independent of btx_lib_mail's
    internal structure.

    Attributes:
        smtp_hosts: List of SMTP servers in 'host[:port]' format. Tried in order until
            one succeeds.
        from_address: Default sender address for outgoing emails.
        smtp_username: Optional SMTP authentication username.
        smtp_password: Optional SMTP authentication password.
        use_starttls: Enable STARTTLS negotiation.
        timeout: Socket timeout in seconds for SMTP operations.
        raise_on_missing_attachments: When True, missing attachment files raise FileNotFoundError.
        raise_on_invalid_recipient: When True, invalid email addresses raise ValueError.
        default_recipients: Default email recipients for notifications.

    Example:
        >>> config = EmailConfig(
        ...     smtp_hosts=["smtp.example.com:587"],
        ...     from_address="noreply@example.com"
        ... )
        >>> config.smtp_hosts
        ['smtp.example.com:587']
    """

    smtp_hosts: list[str] = field(default_factory=_default_smtp_hosts)
    from_address: str = "noreply@localhost"
    smtp_username: str | None = None
    smtp_password: str | None = None
    use_starttls: bool = True
    timeout: float = 30.0
    raise_on_missing_attachments: bool = True
    raise_on_invalid_recipient: bool = True
    default_recipients: list[str] = field(default_factory=lambda: [])

    def __post_init__(self) -> None:
        """Validate configuration values.

        Catch common configuration mistakes early with clear error messages
        rather than allowing invalid values to cause obscure failures later.

        Raises:
            ValueError: When configuration values are invalid.

        Example:
            >>> EmailConfig(timeout=-5.0)  # doctest: +IGNORE_EXCEPTION_DETAIL
            Traceback (most recent call last):
            ...
            ValueError: timeout must be positive, got -5.0

            >>> EmailConfig(from_address="not-an-email")  # doctest: +IGNORE_EXCEPTION_DETAIL
            Traceback (most recent call last):
            ...
            ValueError: from_address must contain @, got 'not-an-email'
        """
        if self.timeout <= 0:
            raise ValueError(f"timeout must be positive, got {self.timeout}")

        if "@" not in self.from_address:
            raise ValueError(f"from_address must contain @, got {self.from_address!r}")

        for host in self.smtp_hosts:
            _validate_smtp_host(host)

    def to_conf_mail(self) -> ConfMail:
        """Convert to btx_lib_mail ConfMail object.

        Isolates the adapter dependency on btx_lib_mail types from the
        rest of the application.

        Returns:
            ConfMail instance configured with current settings.

        Example:
            >>> config = EmailConfig(smtp_hosts=["smtp.example.com"])
            >>> conf = config.to_conf_mail()
            >>> conf.smtphosts
            ['smtp.example.com']
        """
        # Pydantic model type inference limitation in strict mode
        return ConfMail(
            smtphosts=self.smtp_hosts,  # type: ignore[reportUnknownVariableType]
            smtp_username=self.smtp_username,
            smtp_password=self.smtp_password,
            smtp_use_starttls=self.use_starttls,
            smtp_timeout=self.timeout,
            raise_on_missing_attachments=self.raise_on_missing_attachments,
            raise_on_invalid_recipient=self.raise_on_invalid_recipient,
        )


def _resolve_credentials(config: EmailConfig) -> tuple[str, str] | None:
    """Extract credentials tuple from config when both username and password exist."""
    if config.smtp_username and config.smtp_password:
        return (config.smtp_username, config.smtp_password)
    return None


def _normalize_recipients(recipients: str | Sequence[str]) -> str | list[str]:
    """Normalize recipients to a consistent format for logging."""
    return recipients if isinstance(recipients, str) else list(recipients)


def send_email(
    *,
    config: EmailConfig,
    recipients: str | Sequence[str],
    subject: str,
    body: str = "",
    body_html: str = "",
    from_address: str | None = None,
    attachments: Sequence[Path] | None = None,
) -> bool:
    """Send an email using configured SMTP settings.

    Args:
        config: Email configuration with SMTP settings.
        recipients: Single address or sequence of addresses.
        subject: Email subject line.
        body: Plain-text body.
        body_html: HTML body (optional).
        from_address: Override sender (uses config default if None).
        attachments: Optional file paths to attach.

    Returns:
        True on success.

    Raises:
        ValueError: No valid recipients.
        FileNotFoundError: Missing attachment.
        RuntimeError: All SMTP hosts failed.
    """
    sender = from_address if from_address is not None else config.from_address
    normalized_recipients = _normalize_recipients(recipients)

    logger.info(
        "Sending email",
        extra={
            "from": sender,
            "recipients": normalized_recipients,
            "subject": subject,
            "has_html": bool(body_html),
            "attachment_count": len(attachments) if attachments else 0,
        },
    )

    try:
        result = btx_send(
            mail_from=sender,
            mail_recipients=recipients,
            mail_subject=subject,
            mail_body=body,
            mail_body_html=body_html,
            smtphosts=config.smtp_hosts,
            attachment_file_paths=attachments,
            credentials=_resolve_credentials(config),
            use_starttls=config.use_starttls,
            timeout=config.timeout,
        )
        logger.info("Email sent successfully", extra={"from": sender, "recipients": normalized_recipients})
        return result

    except Exception as e:
        logger.error("Failed to send email", extra={"error": str(e), "from": sender, "recipients": normalized_recipients}, exc_info=True)
        raise


def send_notification(
    *,
    config: EmailConfig,
    recipients: str | Sequence[str],
    subject: str,
    message: str,
) -> bool:
    """Send a simple plain-text notification email.

    Convenience wrapper for the common case of sending simple notifications
    without HTML or attachments.

    Args:
        config: Email configuration containing SMTP settings.
        recipients: Single recipient address or sequence of addresses.
        subject: Email subject line.
        message: Plain-text notification message.

    Returns:
        Always True when delivery succeeds. Failures raise exceptions.

    Raises:
        ValueError: No valid recipients remain after validation.
        RuntimeError: All SMTP hosts failed for a recipient.

    Side Effects:
        Sends email via SMTP. Logs send attempts.

    Example:
        >>> from unittest.mock import patch
        >>> config = EmailConfig(
        ...     smtp_hosts=["smtp.example.com"],
        ...     from_address="alerts@example.com"
        ... )
        >>> with patch("smtplib.SMTP"):
        ...     result = send_notification(
        ...         config=config,
        ...         recipients="admin@example.com",
        ...         subject="System Alert",
        ...         message="Deployment completed successfully"
        ...     )
        >>> result
        True
    """
    return send_email(
        config=config,
        recipients=recipients,
        subject=subject,
        body=message,
    )


def _convert_to_string_list(items: list[Any]) -> list[str]:
    """Convert list items to strings, filtering empty values."""
    return [str(item) for item in items if item]  # type: ignore[arg-type]


def _try_parse_json_list(json_str: str) -> list[str]:
    """Try to parse a JSON string as a list of strings."""
    import json

    try:
        parsed = json.loads(json_str)
        return _convert_to_string_list(list(parsed)) if isinstance(parsed, list) else []  # type: ignore[reportUnknownArgumentType]
    except json.JSONDecodeError:
        return []


def _parse_string_list(raw: Any) -> list[str]:
    """Parse a string list from config, handling JSON strings from .env files."""
    if isinstance(raw, list):
        return _convert_to_string_list(list(raw))  # type: ignore[reportUnknownArgumentType]

    if isinstance(raw, str) and raw.startswith("["):
        return _try_parse_json_list(raw)

    return []


def _parse_string(raw: Any, default: str) -> str:
    """Parse a string value with fallback to default."""
    return raw if isinstance(raw, str) else default


def _parse_optional_string(raw: Any) -> str | None:
    """Parse an optional string value."""
    return raw if isinstance(raw, str) else None


def _parse_bool(raw: Any, default: bool) -> bool:
    """Parse a boolean value with fallback to default."""
    return raw if isinstance(raw, bool) else default


def _parse_float(raw: Any, default: float) -> float:
    """Parse a float value with fallback to default."""
    return float(raw) if isinstance(raw, (int, float)) else default


def load_email_config_from_dict(config_dict: Mapping[str, Any]) -> EmailConfig:
    """Load EmailConfig from a configuration dictionary.

    Bridges lib_layered_config's dictionary output with the typed
    EmailConfig dataclass, handling optional values and type conversions.

    Args:
        config_dict: Configuration dictionary typically from lib_layered_config.
            Expected to have an 'email' section with email settings.

    Returns:
        Configured email settings with defaults for missing values.

    Example:
        >>> config_dict = {
        ...     "email": {
        ...         "smtp_hosts": ["smtp.example.com:587"],
        ...         "from_address": "test@example.com"
        ...     }
        ... }
        >>> email_config = load_email_config_from_dict(config_dict)
        >>> email_config.from_address
        'test@example.com'
        >>> email_config.use_starttls
        True
    """
    email_section_raw = config_dict.get("email", {})
    section: Mapping[str, Any] = cast(Mapping[str, Any], email_section_raw if isinstance(email_section_raw, dict) else {})

    return EmailConfig(
        smtp_hosts=_parse_string_list(section.get("smtp_hosts", [])),
        from_address=_parse_string(section.get("from_address"), "noreply@localhost"),
        smtp_username=_parse_optional_string(section.get("smtp_username")),
        smtp_password=_parse_optional_string(section.get("smtp_password")),
        use_starttls=_parse_bool(section.get("use_starttls", True), True),
        timeout=_parse_float(section.get("timeout", 30.0), 30.0),
        raise_on_missing_attachments=_parse_bool(section.get("raise_on_missing_attachments", True), True),
        raise_on_invalid_recipient=_parse_bool(section.get("raise_on_invalid_recipient", True), True),
        default_recipients=_parse_string_list(section.get("default_recipients", [])),
    )


__all__ = [
    "EmailConfig",
    "send_email",
    "send_notification",
    "load_email_config_from_dict",
]
