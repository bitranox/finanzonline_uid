"""Email sending adapter using btx_lib_mail.

Provides a clean wrapper around btx_lib_mail that integrates with the
application's configuration system and logging infrastructure. Isolates
email functionality behind a domain-appropriate interface.

Contents:
    * :class:`EmailSection` - the ``[email]`` section as read from the configuration
    * :class:`EmailConfig` - Configuration container for email settings
    * :func:`load_email_config` - build an EmailConfig from the layered configuration
    * :func:`send_email` - Primary email sending interface
    * :func:`send_notification` - Convenience wrapper for simple notifications

System Role:
    Acts as the email adapter layer, bridging btx_lib_mail with the application's
    configuration and logging systems while keeping domain logic decoupled from
    email mechanics.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from btx_lib_mail.lib_mail import ConfMail, Transport
from btx_lib_mail.lib_mail import send as btx_send
from lib_layered_config import Config
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_core import PydanticUseDefault

from .config import empty_text_list, number_or_default, parse_string_list, read_config_section, text_setting
from .enums import ConfigSection

logger = logging.getLogger(__name__)


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
        smtp_password: Optional SMTP authentication password; unwrapped only where
            it is handed to btx_lib_mail, so it never renders in a repr or log.
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

    smtp_hosts: list[str] = field(default_factory=empty_text_list)
    from_address: str = "noreply@localhost"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    use_starttls: bool = True
    timeout: float = 30.0
    raise_on_missing_attachments: bool = True
    raise_on_invalid_recipient: bool = True
    default_recipients: list[str] = field(default_factory=empty_text_list)

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
        return ConfMail(
            smtphosts=self.smtp_hosts,
            smtp_username=self.smtp_username,
            smtp_password=self.smtp_password,
            smtp_use_starttls=self.use_starttls,
            smtp_timeout=self.timeout,
            raise_on_missing_attachments=self.raise_on_missing_attachments,
            raise_on_invalid_recipient=self.raise_on_invalid_recipient,
        )


def _resolve_credentials(config: EmailConfig) -> tuple[str, str] | None:
    """Extract credentials tuple from config when both username and password exist.

    The password is unwrapped here because btx_lib_mail's ``send`` takes it as text.
    """
    password = config.smtp_password.get_secret_value() if config.smtp_password is not None else ""
    if config.smtp_username and password:
        return (config.smtp_username, password)
    return None


def _normalize_recipients(recipients: str | Sequence[str]) -> str | list[str]:
    """Normalize recipients to a consistent format for logging."""
    return recipients if isinstance(recipients, str) else list(recipients)


def _validate_attachments_exist(attachments: Sequence[Path] | None) -> None:
    """Validate that all attachment files exist before sending.

    Args:
        attachments: Optional sequence of file paths to validate.

    Raises:
        FileNotFoundError: When any attachment file does not exist.
    """
    if not attachments:
        return
    for path in attachments:
        if not path.exists():
            raise FileNotFoundError(f"Attachment file not found: {path}")


def send_email(
    *,
    config: EmailConfig,
    recipients: str | Sequence[str],
    subject: str,
    body: str = "",
    body_html: str = "",
    from_address: str | None = None,
    attachments: Sequence[Path] | None = None,
    transport: Transport | None = None,
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
        transport: Delivery seam. ``None`` uses btx_lib_mail's production
            smtplib transport; supplying one substitutes the whole SMTP wire
            protocol, which is how delivery is exercised without a live server.

    Returns:
        True on success.

    Raises:
        ValueError: No valid recipients.
        FileNotFoundError: Missing attachment.
        RuntimeError: All SMTP hosts failed.
    """
    if config.raise_on_missing_attachments:
        _validate_attachments_exist(attachments)

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
            transport=transport,
        )
        logger.info("Email sent successfully", extra={"from": sender, "recipients": normalized_recipients})
        return result

    except Exception as e:
        logger.exception("Failed to send email", extra={"error": str(e), "from": sender, "recipients": normalized_recipients})
        raise


def send_notification(
    *,
    config: EmailConfig,
    recipients: str | Sequence[str],
    subject: str,
    message: str,
    transport: Transport | None = None,
) -> bool:
    """Send a simple plain-text notification email.

    Convenience wrapper for the common case of sending simple notifications
    without HTML or attachments.

    Args:
        config: Email configuration containing SMTP settings.
        recipients: Single recipient address or sequence of addresses.
        subject: Email subject line.
        message: Plain-text notification message.
        transport: Delivery seam forwarded to :func:`send_email`.

    Returns:
        Always True when delivery succeeds. Failures raise exceptions.

    Raises:
        ValueError: No valid recipients remain after validation.
        RuntimeError: All SMTP hosts failed for a recipient.

    Side Effects:
        Sends email via SMTP. Logs send attempts.

    Example:
        A transport stands in for the SMTP server, so the example delivers a
        real composed message without touching the network.

        >>> class CollectingTransport:
        ...     def __init__(self):
        ...         self.recipients = []
        ...     def deliver(self, *, host, sender, recipient, message, delivery):
        ...         self.recipients.append(recipient)
        >>> config = EmailConfig(
        ...     smtp_hosts=["smtp.example.com"],
        ...     from_address="alerts@example.com"
        ... )
        >>> transport = CollectingTransport()
        >>> send_notification(
        ...     config=config,
        ...     recipients="admin@example.com",
        ...     subject="System Alert",
        ...     message="Deployment completed successfully",
        ...     transport=transport,
        ... )
        True
        >>> transport.recipients
        ['admin@example.com']
    """
    return send_email(
        config=config,
        recipients=recipients,
        subject=subject,
        body=message,
        transport=transport,
    )


class EmailSection(BaseModel):
    """The ``[email]`` section as read from the layered configuration.

    Each setting of the wrong type falls back to its default instead of failing,
    so building the section never raises; the value checks (a positive timeout, a
    sender with ``@``, a valid ``host:port``) stay in :class:`EmailConfig`, which
    raises them as ``ValueError`` for configured and hand-built settings alike.

    Examples:
        >>> section = EmailSection.model_validate({"timeout": "slow", "use_starttls": "yes", "smtp_password": 4711})
        >>> section.timeout, section.use_starttls, section.smtp_password
        (30.0, True, SecretStr('**********'))
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    smtp_hosts: list[str] = Field(default_factory=empty_text_list)
    from_address: str = "noreply@localhost"
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    use_starttls: bool = True
    timeout: float = 30.0
    raise_on_missing_attachments: bool = True
    raise_on_invalid_recipient: bool = True
    default_recipients: list[str] = Field(default_factory=empty_text_list)

    @field_validator("smtp_hosts", "default_recipients", mode="before")
    @classmethod
    def _text_list(cls, raw: object) -> list[str]:
        return parse_string_list(raw)

    @field_validator("from_address", mode="before")
    @classmethod
    def _sender(cls, raw: object) -> str:
        if isinstance(raw, str):
            return raw
        raise PydanticUseDefault

    @field_validator("smtp_username", "smtp_password", mode="before")
    @classmethod
    def _credential(cls, raw: object) -> str | None:
        return text_setting(raw)

    @field_validator("use_starttls", "raise_on_missing_attachments", "raise_on_invalid_recipient", mode="before")
    @classmethod
    def _flag(cls, raw: object) -> bool:
        if isinstance(raw, bool):
            return raw
        raise PydanticUseDefault

    @field_validator("timeout", mode="before")
    @classmethod
    def _timeout(cls, raw: object) -> float:
        return number_or_default(raw)


def load_email_config(config: Config) -> EmailConfig:
    """Load EmailConfig from the ``[email]`` section of the layered configuration.

    Args:
        config: Loaded layered configuration.

    Returns:
        Configured email settings with defaults for missing or mistyped values.

    Raises:
        ValueError: When a configured value is invalid (see :class:`EmailConfig`).

    Example:
        >>> config = Config({"email": {"smtp_hosts": ["smtp.example.com:587"], "from_address": "test@example.com"}}, {})
        >>> email_config = load_email_config(config)
        >>> email_config.from_address
        'test@example.com'
        >>> email_config.use_starttls
        True
    """
    section = EmailSection.model_validate(dict(read_config_section(config, ConfigSection.EMAIL)))
    return EmailConfig(
        smtp_hosts=list(section.smtp_hosts),
        from_address=section.from_address,
        smtp_username=section.smtp_username,
        smtp_password=section.smtp_password,
        use_starttls=section.use_starttls,
        timeout=section.timeout,
        raise_on_missing_attachments=section.raise_on_missing_attachments,
        raise_on_invalid_recipient=section.raise_on_invalid_recipient,
        default_recipients=list(section.default_recipients),
    )


__all__ = [
    "EmailConfig",
    "EmailSection",
    "load_email_config",
    "send_email",
    "send_notification",
]
