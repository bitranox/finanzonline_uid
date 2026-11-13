"""HTML template constants and helper functions.

Purpose
-------
Provide shared HTML templates, styles, and colors used across
formatters and email notifications, plus the one classification of a
return code into a :class:`ResultStatus` that every formatter uses.

System Role
-----------
Adapters layer - shared constants for HTML formatting.
"""

from __future__ import annotations

import html
from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from finanzonline_uid.domain.return_codes import ReturnCode, Severity
from finanzonline_uid.i18n import N_, _

if TYPE_CHECKING:
    from finanzonline_uid.domain.models import Address

__all__ = [
    "COLOR_GRAY",
    "COLOR_GREEN",
    "COLOR_RED",
    "COLOR_YELLOW",
    "HTML_BODY_STYLE",
    "HTML_DOCTYPE",
    "HTML_TABLE_STYLE",
    "HTML_TD_STYLE",
    "RATE_LIMITED_CODES",
    "RESULT_STATUS_COLORS",
    "RESULT_STATUS_LABELS",
    "SERVICE_UNAVAILABLE_CODES",
    "SEVERITY_COLORS",
    "ResultStatus",
    "classify_result",
    "format_address_row_html",
    "get_html_footer",
    "get_severity_color",
    "html_row",
    "result_status_label",
]

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


class ResultStatus(str, Enum):
    """Outcome category of a UID check, derived from its FinanzOnline return code.

    The value is an identifier only; the text shown to a reader comes from
    :data:`RESULT_STATUS_LABELS` (translated) or from a caller's own wording.

    Examples:
        >>> ResultStatus.RATE_LIMITED.value
        'rate_limited'
    """

    VALID = "valid"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


# N_ only marks the labels for extraction; result_status_label() translates them at
# render time, because the active language is known only then.
RESULT_STATUS_LABELS: Final[Mapping[ResultStatus, str]] = MappingProxyType(
    {
        ResultStatus.VALID: N_("VALID"),
        ResultStatus.INVALID: N_("INVALID"),
        ResultStatus.UNAVAILABLE: N_("UNAVAILABLE"),
        ResultStatus.RATE_LIMITED: N_("RATE LIMITED"),
        ResultStatus.ERROR: N_("ERROR"),
    }
)

# Badge colour per status in HTML output
RESULT_STATUS_COLORS: Final[Mapping[ResultStatus, str]] = MappingProxyType(
    {
        ResultStatus.VALID: COLOR_GREEN,
        ResultStatus.INVALID: COLOR_RED,
        ResultStatus.UNAVAILABLE: COLOR_GRAY,
        ResultStatus.RATE_LIMITED: COLOR_YELLOW,
        ResultStatus.ERROR: COLOR_RED,
    }
)

# Text colour per severity in HTML output
SEVERITY_COLORS: Final[Mapping[Severity, str]] = MappingProxyType(
    {
        Severity.SUCCESS: COLOR_GREEN,
        Severity.WARNING: COLOR_YELLOW,
        Severity.ERROR: COLOR_RED,
        Severity.CRITICAL: COLOR_RED,
    }
)


def classify_result(return_code: int) -> ResultStatus:
    """Classify a FinanzOnline return code into a result status.

    Args:
        return_code: FinanzOnline return code.

    Returns:
        The status category. Every code that is not valid, invalid,
        unavailable or rate limited is an error.

    Examples:
        >>> [classify_result(code).value for code in (0, 1, -2, 1514, -4)]
        ['valid', 'invalid', 'unavailable', 'rate_limited', 'error']
    """
    if return_code == ReturnCode.UID_VALID:
        return ResultStatus.VALID
    if return_code == ReturnCode.UID_INVALID:
        return ResultStatus.INVALID
    if return_code in SERVICE_UNAVAILABLE_CODES:
        return ResultStatus.UNAVAILABLE
    if return_code in RATE_LIMITED_CODES:
        return ResultStatus.RATE_LIMITED
    return ResultStatus.ERROR


def result_status_label(status: ResultStatus) -> str:
    """Return the translated display label of a result status.

    Args:
        status: Result status to label.

    Returns:
        Translated label, e.g. ``VALID`` in English.
    """
    return _(RESULT_STATUS_LABELS[status])


def get_severity_color(severity: Severity) -> str:
    """Get HTML color for severity level.

    Args:
        severity: Severity of the return code.

    Returns:
        Hex color code for the severity.

    Examples:
        >>> get_severity_color(Severity.WARNING)
        '#ffc107'
    """
    return SEVERITY_COLORS[severity]


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


def format_address_row_html(address: Address | None) -> str:
    """Format address as HTML table row, or empty string if no address.

    Args:
        address: Address object or None.

    Returns:
        HTML table row string with address, or empty string.
    """
    if address is None:
        return ""
    address_lines = address.as_lines()
    if not address_lines:
        return ""
    # Escape each address line to prevent HTML injection
    address_html = "<br>".join(html.escape(line) for line in address_lines)
    return f"<tr><td style='padding: 8px 15px; font-weight: bold; vertical-align: top;'>{_('Address:')}</td><td style='padding: 8px 15px;'>{address_html}</td></tr>"
