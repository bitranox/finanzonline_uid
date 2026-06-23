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
from typing import TYPE_CHECKING

from finanzonline_uid.adapters.formatting import format_result_html
from finanzonline_uid.adapters.formatting.html_templates import (
    RATE_LIMITED_CODES,
    SERVICE_UNAVAILABLE_CODES,
)
from finanzonline_uid.adapters.notification.error_html_formatter import format_error_html
from finanzonline_uid.adapters.notification.plain_formatter import format_error_plain, format_result_plain
from finanzonline_uid.adapters.notification.rate_limit_formatter import (
    format_rate_limit_warning_html,
    format_rate_limit_warning_plain,
)
from finanzonline_uid.domain.return_codes import ReturnCode, get_return_code_info
from finanzonline_uid.enums import EmailFormat
from finanzonline_uid.i18n import _
from finanzonline_uid.mail import EmailConfig, send_email

if TYPE_CHECKING:
    from finanzonline_uid.adapters.ratelimit import RateLimitStatus
    from finanzonline_uid.domain.models import Diagnostics, UidCheckResult


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
    if return_code == ReturnCode.UID_VALID:
        return _("Valid")
    if return_code == ReturnCode.UID_INVALID:
        return _("Invalid")
    if return_code in SERVICE_UNAVAILABLE_CODES:
        return _("Service Unavailable")
    if return_code in RATE_LIMITED_CODES:
        return _("Rate Limited")

    # For other error codes, use the meaning from return code info
    info = get_return_code_info(return_code)
    return info.meaning


class EmailNotificationAdapter:
    """Email notification adapter implementing NotificationPort.

    Sends UID verification results via email using btx_lib_mail.

    Attributes:
        _config: Email configuration settings.
        _email_format: Email body format (html, text, or both).
    """

    def __init__(
        self,
        config: EmailConfig,
        email_format: EmailFormat = EmailFormat.HTML,
    ) -> None:
        """Initialize email notification adapter.

        Args:
            config: Email configuration with SMTP settings.
            email_format: Email body format - html, text, or both.
        """
        self._config = config
        self._email_format = email_format

    def _get_body_parts(self, plain_body: str, html_body: str) -> tuple[str, str]:
        """Get body parts based on configured email format.

        Args:
            plain_body: Plain text body content.
            html_body: HTML body content.

        Returns:
            Tuple of (plain_body, html_body) with empty string for excluded format.
        """
        if self._email_format == EmailFormat.PLAIN:
            return plain_body, ""
        if self._email_format == EmailFormat.HTML:
            return "", html_body
        return plain_body, html_body

    def send_result(
        self,
        result: "UidCheckResult",
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

        plain_body, html_body = self._get_body_parts(
            format_result_plain(result),
            format_result_html(result),
        )

        logger.info(
            "Sending UID check notification for %s to %d recipients (format=%s)",
            result.uid,
            len(recipients),
            self._email_format,
        )

        try:
            return send_email(
                config=self._config,
                recipients=recipients,
                subject=subject,
                body=plain_body,
                body_html=html_body,
            )
        except Exception as e:
            logger.error("Failed to send notification: %s", e)
            return False

    def send_error(
        self,
        error_type: str,
        error_message: str,
        uid: str,
        recipients: list[str],
        return_code: int | None = None,
        retryable: bool = False,
        diagnostics: "Diagnostics | None" = None,
    ) -> bool:
        """Send error notification via email.

        Args:
            error_type: Type of error (e.g., "Authentication Error").
            error_message: Error message details.
            uid: The UID that was being checked.
            recipients: Email addresses to send notification to.
            return_code: Optional return code from BMF.
            retryable: Whether the error is retryable.
            diagnostics: Optional Diagnostics object for debugging.

        Returns:
            True if notification sent successfully, False otherwise.
        """
        if not recipients:
            logger.warning("No recipients specified, skipping error notification")
            return False

        subject = f"UID Check ERROR: {uid} - {error_type}"

        plain_body, html_body = self._get_body_parts(
            format_error_plain(error_type, error_message, uid, return_code, retryable, diagnostics),
            format_error_html(error_type, error_message, uid, return_code, retryable, diagnostics),
        )

        logger.info(
            "Sending UID check error notification for %s to %d recipients (format=%s)",
            uid,
            len(recipients),
            self._email_format,
        )

        try:
            return send_email(
                config=self._config,
                recipients=recipients,
                subject=subject,
                body=plain_body,
                body_html=html_body,
            )
        except Exception as e:
            logger.error("Failed to send error notification: %s", e)
            return False

    def send_rate_limit_warning(
        self,
        status: "RateLimitStatus",
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

        plain_body, html_body = self._get_body_parts(
            format_rate_limit_warning_plain(status),
            format_rate_limit_warning_html(status),
        )

        logger.info(
            "Sending rate limit warning to %d recipients (format=%s, count=%d/%d)",
            len(recipients),
            self._email_format,
            status.current_count,
            status.max_queries,
        )

        try:
            return send_email(
                config=self._config,
                recipients=recipients,
                subject=subject,
                body=plain_body,
                body_html=html_body,
            )
        except Exception as e:
            logger.error("Failed to send rate limit warning: %s", e)
            return False
