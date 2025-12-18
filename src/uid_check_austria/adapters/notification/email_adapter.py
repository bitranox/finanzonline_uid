"""Email notification adapter for UID verification results.

Purpose
-------
Implement NotificationPort for sending UID verification result
notifications via email using btx_lib_mail infrastructure.

Contents
--------
* :class:`EmailNotificationAdapter` - Email notification implementation
* :func:`format_result_plain` - Plain text result formatter
* :func:`format_result_html` - HTML result formatter

System Role
-----------
Adapters layer - integrates with btx_lib_mail for email delivery.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from uid_check_austria._datetime_utils import format_local_time
from uid_check_austria.domain.models import Diagnostics
from uid_check_austria.domain.return_codes import get_return_code_info
from uid_check_austria.enums import EmailFormat
from uid_check_austria.i18n import _
from uid_check_austria.mail import EmailConfig, send_email

if TYPE_CHECKING:
    from uid_check_austria.adapters.ratelimit import RateLimitStatus
    from uid_check_austria.domain.models import Address, UidCheckResult
    from uid_check_austria.domain.return_codes import ReturnCodeInfo


logger = logging.getLogger(__name__)


# HTML template fragments for email formatting
_HTML_DOCTYPE = '<!DOCTYPE html>\n<html>\n<head>\n    <meta charset="utf-8">\n    <title>{title}</title>\n</head>'
_HTML_BODY_STYLE = "font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;"
_HTML_TABLE_STYLE = "width: 100%; border-collapse: collapse; margin: 20px 0;"
_HTML_TD_STYLE = "padding: 8px 15px;"


def _get_html_footer() -> str:
    """Get translated HTML footer."""
    return f'<p style="color: #7f8c8d; font-size: 0.9em; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px;">{_("This is an automated message from uid-check-austria.")}</p>'


def _format_address_plain(address: "Address") -> list[str]:
    """Format address as plain text lines with proper indentation."""
    address_lines = address.as_lines()
    if not address_lines:
        return []
    label = _("Address:")
    padding = " " * len(label)
    return [f"{label} {address_lines[0]}"] + [f"{padding} {line}" for line in address_lines[1:]]


def _format_company_section_plain(result: UidCheckResult) -> list[str]:
    """Format company information section for plain text output."""
    has_name = bool(result.name)
    address = result.address

    if not (has_name or address):
        return []

    lines = ["", _("Company Information"), "-" * 30]
    if has_name:
        lines.append(f"{_('Name:')}    {result.name}")
    if address is not None:
        lines.extend(_format_address_plain(address))
    return lines


def _format_cache_notice_plain(result: UidCheckResult) -> list[str]:
    """Format cached result notice for plain text output."""
    if not result.from_cache or result.cached_at is None:
        return []
    cached_time = format_local_time(result.cached_at)
    return [
        "",
        "=" * 50,
        _("NOTE: This is a CACHED result"),
        f"{_('Originally queried:')} {cached_time}",
        "=" * 50,
    ]


def format_result_plain(result: UidCheckResult) -> str:
    """Format UID check result as plain text.

    Args:
        result: UID verification result to format.

    Returns:
        Plain text representation of the result.
    """
    info = get_return_code_info(result.return_code)
    status = _("VALID") if result.is_valid else _("INVALID")

    lines = [
        _("UID Verification Result (Stufe 2)"),
        "=" * 50,
        "",
        f"{_('UID:')}         {result.uid}",
        _("Query Level: Stufe 2 (with name/address verification)"),
        f"{_('Status:')}      {status}",
        f"{_('Return Code:')} {result.return_code}",
        f"{_('Message:')}     {result.message}",
        f"{_('Severity:')}    {info.severity.value}",
        f"{_('Retryable:')}   {_('Yes') if info.retryable else _('No')}",
        f"{_('Timestamp:')}   {format_local_time(result.timestamp)}",
    ]

    lines.extend(_format_company_section_plain(result))
    lines.extend(_format_cache_notice_plain(result))
    lines.extend(["", "-" * 50, _("This is an automated message from uid-check-austria.")])

    return "\n".join(lines)


def _get_severity_color(severity_value: str) -> str:
    """Get HTML color for severity level."""
    colors = {"success": "#28a745", "warning": "#ffc107", "error": "#dc3545", "critical": "#dc3545"}
    return colors.get(severity_value, "#6c757d")


def _format_address_row_html(address: "Address | None") -> str:
    """Format address as HTML table row, or empty string if no address."""
    if not address:
        return ""
    address_lines = address.as_lines()
    if not address_lines:
        return ""
    address_html = "<br>".join(address_lines)
    return f"<tr><td style='padding: 8px 15px; font-weight: bold; vertical-align: top;'>{_('Address:')}</td><td style='padding: 8px 15px;'>{address_html}</td></tr>"


def _format_company_section_html(result: UidCheckResult) -> str:
    """Format company information section for HTML output."""
    has_name = bool(result.name)
    has_address = result.address is not None

    if not (has_name or has_address):
        return ""

    rows = [f'<tr><td colspan="2"><h3 style="margin: 20px 0 10px 0; color: #333;">{_("Company Information")}</h3></td></tr>']
    if has_name:
        rows.append(f'<tr><td style="{_HTML_TD_STYLE} font-weight: bold;">{_("Name:")}</td><td style="{_HTML_TD_STYLE}">{result.name}</td></tr>')
    if has_address:
        rows.append(_format_address_row_html(result.address))
    return "".join(rows)


def _html_row(label: str, value: str, extra_td_style: str = "") -> str:
    """Build a single HTML table row."""
    td_base = _HTML_TD_STYLE
    return f'<tr><td style="{td_base} font-weight: bold;">{label}</td><td style="{td_base}{extra_td_style}">{value}</td></tr>'


def _build_result_table_rows(result: UidCheckResult, info: "ReturnCodeInfo") -> str:
    """Build HTML table rows for result display."""
    status = _("VALID") if result.is_valid else _("INVALID")
    status_color = "#28a745" if result.is_valid else "#dc3545"
    severity_color = _get_severity_color(info.severity.value)
    status_span = f'<span style="background-color: {status_color}; color: white; padding: 4px 12px; border-radius: 4px; font-weight: bold;">{status}</span>'
    severity_span = f'<span style="color: {severity_color}; font-weight: bold;">{info.severity.value.upper()}</span>'
    rows = [
        _html_row(_("UID:"), result.uid, " font-family: monospace; font-size: 1.1em;"),
        _html_row(_("Query Level:"), _("Stufe 2 (with name/address verification)")),
        _html_row(_("Status:"), status_span),
        _html_row(_("Return Code:"), str(result.return_code)),
        _html_row(_("Message:"), result.message),
        _html_row(_("Severity:"), severity_span),
        _html_row(_("Retryable:"), _("Yes") if info.retryable else _("No")),
        _html_row(_("Timestamp:"), format_local_time(result.timestamp)),
    ]
    return "".join(rows) + _format_company_section_html(result)


def _format_cache_notice_html(result: UidCheckResult) -> str:
    """Format cached result notice as HTML info box."""
    if not result.from_cache or result.cached_at is None:
        return ""
    cached_time = format_local_time(result.cached_at)
    return f"""<div style="background-color: #d1ecf1; border: 1px solid #bee5eb; border-radius: 4px; padding: 15px; margin: 20px 0; color: #0c5460;">
    <strong>&#x1F4BE; {_("Cached Result")}</strong><br>
    <span style="font-size: 0.95em;">{_("This result was retrieved from cache.")} {_("Originally queried:")} <strong>{cached_time}</strong></span>
</div>"""


def format_result_html(result: UidCheckResult) -> str:
    """Format UID check result as HTML."""
    info = get_return_code_info(result.return_code)
    rows = _build_result_table_rows(result, info)
    cache_notice = _format_cache_notice_html(result)
    title = _("UID Verification Result (Stufe 2)")
    return f'{_HTML_DOCTYPE.format(title=title)}<body style="{_HTML_BODY_STYLE}"><h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">{title}</h2><table style="{_HTML_TABLE_STYLE}">{rows}</table>{cache_notice}{_get_html_footer()}</body></html>'


def _format_return_code_section_plain(return_code: int) -> list[str]:
    """Format return code section for plain text error output."""
    info = get_return_code_info(return_code)
    return [f"{_('Return Code:')} {return_code}", f"{_('Meaning:')}     {info.meaning}", f"{_('Severity:')}    {info.severity.value}"]


def _format_diagnostics_section_plain(diagnostics: Diagnostics) -> list[str]:
    """Format diagnostics section for plain text error output."""
    lines = ["", _("Diagnostic Information"), "-" * 30]
    for key, value in diagnostics.as_dict().items():
        lines.append(f"{key.replace('_', ' ').title()}: {value}")
    return lines


def format_error_plain(
    error_type: str,
    error_message: str,
    uid: str,
    return_code: int | None = None,
    retryable: bool = False,
    diagnostics: Diagnostics | None = None,
) -> str:
    """Format error notification as plain text."""
    from datetime import timezone

    lines = [
        _("UID Check ERROR Notification"),
        "=" * 50,
        "",
        f"{_('UID:')}         {uid}",
        f"{_('Status:')}      {_('ERROR')}",
        f"{_('Error Type:')}  {error_type}",
        f"{_('Message:')}     {error_message}",
    ]

    if return_code is not None:
        lines.extend(_format_return_code_section_plain(return_code))

    lines.extend([f"{_('Retryable:')}   {_('Yes') if retryable else _('No')}", f"{_('Timestamp:')}   {format_local_time(datetime.now(timezone.utc))}"])

    if diagnostics and not diagnostics.is_empty:
        lines.extend(_format_diagnostics_section_plain(diagnostics))

    lines.extend(["", "-" * 50, _("This is an automated error notification from uid-check-austria.")])
    return "\n".join(lines)


def _format_return_code_section_html(return_code: int) -> str:
    """Format return code section as HTML table rows."""
    info = get_return_code_info(return_code)
    return f"""
        <tr><td style="padding: 8px 15px; font-weight: bold;">{_("Return Code:")}</td><td style="padding: 8px 15px;">{return_code}</td></tr>
        <tr><td style="padding: 8px 15px; font-weight: bold;">{_("Meaning:")}</td><td style="padding: 8px 15px;">{info.meaning}</td></tr>
        <tr><td style="padding: 8px 15px; font-weight: bold;">{_("Severity:")}</td><td style="padding: 8px 15px;"><span style="color: #dc3545; font-weight: bold;">{info.severity.value.upper()}</span></td></tr>"""


def _format_diagnostics_section_html(diagnostics: Diagnostics) -> str:
    """Format diagnostics section as HTML."""
    rows = "".join(
        f'<tr><td style="padding: 6px 15px; font-weight: bold; color: #666; font-size: 0.9em;">{k.replace("_", " ").title()}:</td>'
        f'<td style="padding: 6px 15px; font-family: monospace; font-size: 0.85em; word-break: break-all;">{v}</td></tr>'
        for k, v in diagnostics.as_dict().items()
    )
    return f"""<h3 style="color: #856404; border-bottom: 1px solid #ffc107; padding-bottom: 8px; margin-top: 30px;">{_("Diagnostic Information")}</h3>
    <table style="width: 100%; border-collapse: collapse; margin: 10px 0; background-color: #fff3cd; border-radius: 4px;">{rows}</table>"""


def _build_error_table_rows(uid: str, error_type: str, error_message: str, return_code: int | None, retryable: bool, timestamp: str) -> str:
    """Build HTML table rows for error display."""
    error_span = f'<span style="background-color: #dc3545; color: white; padding: 4px 12px; border-radius: 4px; font-weight: bold;">{_("ERROR")}</span>'
    rows = [
        _html_row(_("UID:"), uid, " font-family: monospace; font-size: 1.1em;"),
        _html_row(_("Status:"), error_span),
        _html_row(_("Error Type:"), error_type, " color: #dc3545; font-weight: bold;"),
        _html_row(_("Message:"), error_message),
    ]
    if return_code is not None:
        rows.append(_format_return_code_section_html(return_code))
    rows.extend(
        [
            _html_row(_("Retryable:"), _("Yes - try again later") if retryable else _("No")),
            _html_row(_("Timestamp:"), timestamp),
        ]
    )
    return "".join(rows)


def format_error_html(
    error_type: str,
    error_message: str,
    uid: str,
    return_code: int | None = None,
    retryable: bool = False,
    diagnostics: Diagnostics | None = None,
) -> str:
    """Format error notification as HTML."""
    from datetime import timezone

    timestamp = format_local_time(datetime.now(timezone.utc))
    rows = _build_error_table_rows(uid, error_type, error_message, return_code, retryable, timestamp)
    diag_section = _format_diagnostics_section_html(diagnostics) if diagnostics and not diagnostics.is_empty else ""
    title = _("UID Check Error")
    header = _("UID Check ERROR")
    footer = f'<p style="color: #7f8c8d; font-size: 0.9em; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px;">{_("This is an automated error notification from uid-check-austria.")}</p>'
    return f'{_HTML_DOCTYPE.format(title=title)}<body style="{_HTML_BODY_STYLE}"><h2 style="color: #dc3545; border-bottom: 2px solid #dc3545; padding-bottom: 10px;">{header}</h2><table style="{_HTML_TABLE_STYLE}">{rows}</table>{diag_section}{footer}</body></html>'


# ============================================================================
# Rate Limit Warning Formatters
# ============================================================================


def format_rate_limit_warning_plain(status: "RateLimitStatus") -> str:
    """Format rate limit warning as plain text.

    Args:
        status: Current rate limit status.

    Returns:
        Plain text rate limit warning message.
    """
    from datetime import timezone

    timestamp = format_local_time(datetime.now(timezone.utc))

    lines = [
        _("UID Check Austria - Rate Limit Warning"),
        "=" * 50,
        "",
        _("WARNING: Your query rate has exceeded the configured limit."),
        "",
        _("Current Status"),
        "-" * 30,
        f"{_('Queries in window:')} {status.current_count}",
        f"{_('Maximum allowed:')}   {status.max_queries}",
        f"{_('Window duration:')}   {status.window_hours} {_('hours')}",
        f"{_('Timestamp:')}         {timestamp}",
        "",
        _("Fair Use Policy Notice"),
        "-" * 30,
        _(
            '"UID verifications should only be requested at the time when intra-Community tax-exempt supplies or other services are provided to customers in other EU member states - not in advance or in bulk."'
        ),
        "",
        _("Important"),
        "-" * 30,
        _("You are probably not using this program in the right way."),
        "",
        _("UID queries should be made at the time of transaction, not:"),
        f"- {_('In advance for potential future transactions')}",
        f"- {_('In bulk for database validation')}",
        f"- {_('For speculative or exploratory purposes')}",
        "",
        _("This warning is logged locally. The actual BMF service may enforce its own rate limits independently."),
        "",
        "-" * 50,
        _("This is an automated warning from uid-check-austria."),
    ]

    return "\n".join(lines)


def format_rate_limit_warning_html(status: "RateLimitStatus") -> str:
    """Format rate limit warning as HTML.

    Args:
        status: Current rate limit status.

    Returns:
        HTML rate limit warning message.
    """
    from datetime import timezone

    timestamp = format_local_time(datetime.now(timezone.utc))

    status_rows = f"""
        <tr><td style="{_HTML_TD_STYLE} font-weight: bold;">{_("Queries in window:")}</td><td style="{_HTML_TD_STYLE}">{status.current_count}</td></tr>
        <tr><td style="{_HTML_TD_STYLE} font-weight: bold;">{_("Maximum allowed:")}</td><td style="{_HTML_TD_STYLE}">{status.max_queries}</td></tr>
        <tr><td style="{_HTML_TD_STYLE} font-weight: bold;">{_("Window duration:")}</td><td style="{_HTML_TD_STYLE}">{status.window_hours} {_("hours")}</td></tr>
        <tr><td style="{_HTML_TD_STYLE} font-weight: bold;">{_("Timestamp:")}</td><td style="{_HTML_TD_STYLE}">{timestamp}</td></tr>
    """

    warning_box = f"""<div style="background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; padding: 15px; margin: 20px 0; color: #856404;">
    <strong>&#x26A0; {_("Rate Limit Exceeded")}</strong><br>
    <span style="font-size: 0.95em;">{_("Your query rate has exceeded the configured limit.")}</span>
</div>"""

    policy_quote = _(
        '"UID verifications should only be requested at the time when intra-Community tax-exempt supplies or other services are provided to customers in other EU member states - not in advance or in bulk."'
    )
    policy_box = f"""<div style="background-color: #f8f9fa; border-left: 4px solid #6c757d; padding: 15px; margin: 20px 0;">
    <h3 style="margin-top: 0; color: #495057;">{_("Fair Use Policy Notice")}</h3>
    <blockquote style="margin: 10px 0; font-style: italic; color: #666;">
        {policy_quote}
    </blockquote>
</div>"""

    important_box = f"""<div style="background-color: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; padding: 15px; margin: 20px 0; color: #721c24;">
    <strong>&#x2757; {_("Important")}</strong><br>
    <p style="margin: 10px 0 0 0;">{_("You are probably not using this program in the right way.")}</p>
    <p style="margin: 10px 0 0 0;">{_("UID queries should be made at the time of transaction, not:")}</p>
    <ul style="margin: 5px 0;">
        <li>{_("In advance for potential future transactions")}</li>
        <li>{_("In bulk for database validation")}</li>
        <li>{_("For speculative or exploratory purposes")}</li>
    </ul>
</div>"""

    title = _("UID Check Rate Limit Warning")
    header = _("Rate Limit Warning")
    note = _("This warning is logged locally. The actual BMF service may enforce its own rate limits independently.")
    footer = f'<p style="color: #7f8c8d; font-size: 0.9em; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px;">{_("This is an automated warning from uid-check-austria.")}</p>'

    return f"""{_HTML_DOCTYPE.format(title=title)}
<body style="{_HTML_BODY_STYLE}">
    <h2 style="color: #856404; border-bottom: 2px solid #ffc107; padding-bottom: 10px;">&#x26A0; {header}</h2>
    {warning_box}
    <h3 style="color: #333;">{_("Current Status")}</h3>
    <table style="{_HTML_TABLE_STYLE}">{status_rows}</table>
    {policy_box}
    {important_box}
    <p style="color: #6c757d; font-size: 0.9em;">{note}</p>
    {footer}
</body>
</html>"""


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
        email_format: EmailFormat = EmailFormat.BOTH,
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

        status = "VALID" if result.is_valid else "INVALID"
        subject = f"UID Check Result: {result.uid} - {status}"

        plain_body, html_body = self._get_body_parts(
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
        diagnostics: Diagnostics | None = None,
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
            self._email_format.value,
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
            self._email_format.value,
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
