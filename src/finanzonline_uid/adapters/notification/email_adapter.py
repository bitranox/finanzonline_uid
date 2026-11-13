"""Email notification adapter for UID verification results.

Purpose
-------
Implement NotificationPort for sending UID verification result
notifications via email using btx_lib_mail infrastructure.

Contents
--------
* :class:`EmailNotificationAdapter` - Email notification implementation

System Role
-----------
Adapters layer - integrates with btx_lib_mail for email delivery.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

from finanzonline_uid.adapters.formatting import format_result_html
from finanzonline_uid.adapters.formatting.html_templates import ResultStatus, classify_result
from finanzonline_uid.adapters.notification.error_html_formatter import format_error_html
from finanzonline_uid.adapters.notification.plain_formatter import format_error_plain, format_result_plain
from finanzonline_uid.adapters.notification.rate_limit_formatter import (
    format_rate_limit_warning_html,
    format_rate_limit_warning_plain,
)
from finanzonline_uid.domain.return_codes import get_return_code_info
from finanzonline_uid.enums import EmailFormat
from finanzonline_uid.i18n import _
from finanzonline_uid.mail import EmailConfig, send_email

if TYPE_CHECKING:
    from btx_lib_mail.lib_mail import Transport

    from finanzonline_uid.adapters.ratelimit import RateLimitStatus
    from finanzonline_uid.domain.errors import CheckErrorInfo
    from finanzonline_uid.domain.models import UidCheckResult

__all__ = ["EmailNotificationAdapter"]

logger = logging.getLogger(__name__)


def _get_result_subject_status(return_code: int) -> str:
    """Get a descriptive subject status based on return code.

    Args:
        return_code: FinanzOnline return code.

    Returns:
        Short description suitable for email subject.

    Examples:
        >>> _get_result_subject_status(0)  # doctest: +SKIP
        'Valid'
        >>> _get_result_subject_status(1511)  # doctest: +SKIP
        'Service Unavailable'
    """
    # The subject words differ from the body's status badge (title case, longer
    # wording), so they are spelled out here rather than taken from the label map.
    status = classify_result(return_code)
    if status == ResultStatus.VALID:
        return _("Valid")
    if status == ResultStatus.INVALID:
        return _("Invalid")
    if status == ResultStatus.UNAVAILABLE:
        return _("Service Unavailable")
    if status == ResultStatus.RATE_LIMITED:
        return _("Rate Limited")
    # An error says more through its own meaning than through a generic word
    return get_return_code_info(return_code).meaning


class _BodyParts(NamedTuple):
    """Email bodies to send; an empty string leaves that part out."""

    plain: str
    html: str


class EmailNotificationAdapter:
    """Email notification adapter implementing NotificationPort.

    Sends UID verification results via email using btx_lib_mail.

    Attributes:
        _config: Email configuration settings.
        _email_format: Email body format (html, text, or both).
        _transport: Delivery seam handed to :func:`send_email`.
    """

    def __init__(
        self,
        config: EmailConfig,
        email_format: EmailFormat = EmailFormat.HTML,
        *,
        transport: Transport | None = None,
    ) -> None:
        """Initialize email notification adapter.

        Args:
            config: Email configuration with SMTP settings.
            email_format: Email body format - html, text, or both.
            transport: Delivery seam forwarded to :func:`send_email`. ``None``
                delivers over SMTP; another transport receives the composed
                message instead, which is how a whole CLI run is checked down
                to the bytes it would send.
        """
        self._config = config
        self._email_format = email_format
        self._transport = transport

    def _get_body_parts(self, plain_body: str, html_body: str) -> _BodyParts:
        """Get body parts based on configured email format.

        Args:
            plain_body: Plain text body content.
            html_body: HTML body content.

        Returns:
            The bodies to send, with an empty string for the excluded format.
        """
        if self._email_format == EmailFormat.PLAIN:
            return _BodyParts(plain=plain_body, html="")
        if self._email_format == EmailFormat.HTML:
            return _BodyParts(plain="", html=html_body)
        return _BodyParts(plain=plain_body, html=html_body)

    def send_result(
        self,
        result: UidCheckResult,
        recipients: list[str],
    ) -> bool:
        """Send verification result notification via email.

        Args:
            result: UID verification result to send.
            recipients: Email addresses to send notification to.

        Returns:
            True if notification sent successfully, False otherwise.
        """
        if not recipients:
            logger.warning("No recipients specified, skipping notification")
            return False

        subject_status = _get_result_subject_status(result.return_code)
        subject = f"UID Check Result: {result.uid} - {subject_status}"

        bodies = self._get_body_parts(
            format_result_plain(result),
            format_result_html(result),
        )

        logger.info(
            "Sending UID check notification for %s to %d recipients (format=%s)",
            result.uid,
            len(recipients),
            self._email_format.value,
        )

        try:
            return send_email(
                config=self._config,
                recipients=recipients,
                subject=subject,
                body=bodies.plain,
                body_html=bodies.html,
                transport=self._transport,
            )
        except Exception as e:  # noqa: BLE001 - email delivery is non-fatal, degrade to a bool result
            logger.error("Failed to send notification: %s", e)
            return False

    def send_error(
        self,
        info: CheckErrorInfo,
        uid: str,
        recipients: list[str],
    ) -> bool:
        """Send error notification via email.

        Args:
            info: The failure to report: kind, message, return code,
                retryability and diagnostics.
            uid: The UID that was being checked.
            recipients: Email addresses to send notification to.

        Returns:
            True if notification sent successfully, False otherwise.
        """
        if not recipients:
            logger.warning("No recipients specified, skipping error notification")
            return False

        subject = f"UID Check ERROR: {uid} - {info.error_type.value}"

        bodies = self._get_body_parts(
            format_error_plain(info, uid),
            format_error_html(info, uid),
        )

        logger.info(
            "Sending UID check error notification for %s to %d recipients (format=%s)",
            uid,
            len(recipients),
            self._email_format.value,
        )

        try:
            return send_email(
                config=self._config,
                recipients=recipients,
                subject=subject,
                body=bodies.plain,
                body_html=bodies.html,
                transport=self._transport,
            )
        except Exception as e:  # noqa: BLE001 - email delivery is non-fatal, degrade to a bool result
            logger.error("Failed to send error notification: %s", e)
            return False

    def send_rate_limit_warning(
        self,
        status: RateLimitStatus,
        recipients: list[str],
    ) -> bool:
        """Send rate limit warning notification via email.

        Args:
            status: Current rate limit status.
            recipients: Email addresses to send notification to.

        Returns:
            True if notification sent successfully, False otherwise.
        """
        if not recipients:
            logger.warning("No recipients specified, skipping rate limit warning")
            return False

        subject = "UID Check WARNING: Rate Limit Exceeded"

        bodies = self._get_body_parts(
            format_rate_limit_warning_plain(status),
            format_rate_limit_warning_html(status),
        )

        logger.info(
            "Sending rate limit warning to %d recipients (format=%s, count=%d/%d)",
            len(recipients),
            self._email_format.value,
            status.current_count,
            status.max_queries,
        )

        try:
            return send_email(
                config=self._config,
                recipients=recipients,
                subject=subject,
                body=bodies.plain,
                body_html=bodies.html,
                transport=self._transport,
            )
        except Exception as e:  # noqa: BLE001 - email delivery is non-fatal, degrade to a bool result
            logger.error("Failed to send rate limit warning: %s", e)
            return False
