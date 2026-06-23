"""HTML template constants and helper functions.

Purpose
-------
Provide shared HTML templates, styles, and colors used across
formatters and email notifications.

System Role
-----------
Adapters layer - shared constants for HTML formatting.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from finanzonline_uid.domain.return_codes import ReturnCode
from finanzonline_uid.i18n import N_, _

if TYPE_CHECKING:
    from finanzonline_uid.domain.models import Address


# HTML document template fragments
HTML_DOCTYPE = '<!DOCTYPE html>\n<html>\n<head>\n    <meta charset="utf-8">\n    <title>{title}</title>\n</head>'
HTML_BODY_STYLE = "font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;"
HTML_TABLE_STYLE = "width: 100%; border-collapse: collapse; margin: 20px 0;"
HTML_TD_STYLE = "padding: 8px 15px;"

# Status and severity colors for HTML output
COLOR_GREEN = "#28a745"  # success, valid
COLOR_RED = "#dc3545"  # error, invalid, critical
COLOR_YELLOW = "#ffc107"  # warning, rate limited
COLOR_GRAY = "#6c757d"  # unavailable, neutral


# Return codes that indicate service/system unavailability
SERVICE_UNAVAILABLE_CODES: frozenset[int] = frozenset(
    {
        ReturnCode.SERVICE_UNAVAILABLE,  # 1511
        ReturnCode.TOO_MANY_QUERIES_SERVER,  # 1512
        ReturnCode.SYSTEM_MAINTENANCE,  # -2
    }
)

# Return codes that indicate rate limiting
RATE_LIMITED_CODES: frozenset[int] = frozenset(
    {
        ReturnCode.RATE_LIMIT_UID_EXCEEDED,  # 1513
        ReturnCode.RATE_LIMIT_REQUESTER_EXCEEDED,  # 1514
    }
)

# Status labels with translation markers
_STATUS_VALID = N_("VALID")
_STATUS_INVALID = N_("INVALID")
_STATUS_UNAVAILABLE = N_("UNAVAILABLE")
_STATUS_RATE_LIMITED = N_("RATE LIMITED")
_STATUS_ERROR = N_("ERROR")


def get_result_status(return_code: int) -> str:
    """Determine the appropriate status label based on return code.

    Args:
        return_code: FinanzOnline return code.

    Returns:
        Translated status label appropriate for the return code.
    """
    if return_code == ReturnCode.UID_VALID:
        return _(_STATUS_VALID)
    if return_code == ReturnCode.UID_INVALID:
        return _(_STATUS_INVALID)
    if return_code in SERVICE_UNAVAILABLE_CODES:
        return _(_STATUS_UNAVAILABLE)
    if return_code in RATE_LIMITED_CODES:
        return _(_STATUS_RATE_LIMITED)
    return _(_STATUS_ERROR)


def get_status_color(return_code: int) -> str:
    """Get the appropriate color for a status badge based on return code.

    Args:
        return_code: FinanzOnline return code.

    Returns:
        Hex color code for the status badge.
    """
    if return_code == ReturnCode.UID_VALID:
        return COLOR_GREEN
    if return_code == ReturnCode.UID_INVALID:
        return COLOR_RED
    if return_code in SERVICE_UNAVAILABLE_CODES:
        return COLOR_GRAY
    if return_code in RATE_LIMITED_CODES:
        return COLOR_YELLOW
    return COLOR_RED


def get_severity_color(severity_value: str) -> str:
    """Get HTML color for severity level.

    Args:
        severity_value: Severity string (success, warning, error, critical).

    Returns:
        Hex color code for the severity.
    """
    colors = {"success": COLOR_GREEN, "warning": COLOR_YELLOW, "error": COLOR_RED, "critical": COLOR_RED}
    return colors.get(severity_value, COLOR_GRAY)


def get_html_footer() -> str:
    """Get translated HTML footer."""
    return f'<p style="color: #7f8c8d; font-size: 0.9em; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px;">{_("This is an automated message from finanzonline-uid.")}</p>'


def html_row(label: str, value: str, extra_td_style: str = "", escape_value: bool = True) -> str:
    """Build a single HTML table row.

    Args:
        label: Row label (assumed safe - from translations).
        value: Row value to display.
        extra_td_style: Additional CSS for value cell.
        escape_value: If True (default), HTML-escape the value.

    Returns:
        HTML table row string.
    """
    td_base = HTML_TD_STYLE
    safe_value = html.escape(value) if escape_value else value
    return f'<tr><td style="{td_base} font-weight: bold;">{label}</td><td style="{td_base}{extra_td_style}">{safe_value}</td></tr>'


def format_address_row_html(address: "Address | None") -> str:
    """Format address as HTML table row, or empty string if no address.

    Args:
        address: Address object or None.

    Returns:
        HTML table row string with address, or empty string.
    """
    # Import here to avoid circular imports with domain models
    from finanzonline_uid.domain.models import Address as AddressType

    if not isinstance(address, AddressType):
        return ""
    address_lines = address.as_lines()
    if not address_lines:
        return ""
    # Escape each address line to prevent HTML injection
    address_html = "<br>".join(html.escape(line) for line in address_lines)
    return f"<tr><td style='padding: 8px 15px; font-weight: bold; vertical-align: top;'>{_('Address:')}</td><td style='padding: 8px 15px;'>{address_html}</td></tr>"
