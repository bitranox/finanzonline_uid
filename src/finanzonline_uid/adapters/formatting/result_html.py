"""HTML result formatting.

Purpose
-------
Format UID verification results as HTML documents suitable for
display in browsers, emails, or file output.

System Role
-----------
Adapters layer - transforms domain models into HTML output.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from finanzonline_uid._datetime_utils import format_local_time
from finanzonline_uid.domain.return_codes import get_return_code_info
from finanzonline_uid.i18n import _

from .html_templates import (
    HTML_BODY_STYLE,
    HTML_DOCTYPE,
    HTML_TABLE_STYLE,
    HTML_TD_STYLE,
    format_address_row_html,
    get_html_footer,
    get_result_status,
    get_severity_color,
    get_status_color,
    html_row,
)

if TYPE_CHECKING:
    from finanzonline_uid.domain.models import UidCheckResult
    from finanzonline_uid.domain.return_codes import ReturnCodeInfo


def _format_company_section_html(result: "UidCheckResult") -> str:
    """Format company information section for HTML output."""
    has_name = bool(result.name)
    has_address = result.address is not None

    if not (has_name or has_address):
        return ""

    rows = [f'<tr><td colspan="2"><h3 style="margin: 20px 0 10px 0; color: #333;">{_("Company Information")}</h3></td></tr>']
    if has_name:
        # Escape company name to prevent HTML injection
        escaped_name = html.escape(result.name)
        rows.append(f'<tr><td style="{HTML_TD_STYLE} font-weight: bold;">{_("Name:")}</td><td style="{HTML_TD_STYLE}">{escaped_name}</td></tr>')
    if has_address:
        rows.append(format_address_row_html(result.address))
    return "".join(rows)


def _format_cache_notice_html(result: "UidCheckResult") -> str:
    """Format cached result notice as HTML info box."""
    if not result.from_cache or result.cached_at is None:
        return ""
    cached_time = format_local_time(result.cached_at)
    return f"""<div style="background-color: #d1ecf1; border: 1px solid #bee5eb; border-radius: 4px; padding: 15px; margin: 20px 0; color: #0c5460;">
    <strong>&#x1F4BE; {_("Cached Result")}</strong><br>
    <span style="font-size: 0.95em;">{_("This result was retrieved from cache.")} {_("Originally queried:")} <strong>{cached_time}</strong></span>
</div>"""


def _build_result_table_rows(result: "UidCheckResult", info: "ReturnCodeInfo") -> str:
    """Build HTML table rows for result display."""
    status = get_result_status(result.return_code)
    status_color = get_status_color(result.return_code)
    severity_color = get_severity_color(info.severity)
    status_span = (
        f'<span style="background-color: {status_color}; color: white; padding: 4px 12px; border-radius: 4px; font-weight: bold;">{html.escape(status)}</span>'
    )
    severity_span = f'<span style="color: {severity_color}; font-weight: bold;">{html.escape(info.severity.upper())}</span>'
    rows = [
        html_row(_("UID:"), result.uid, " font-family: monospace; font-size: 1.1em;"),
        html_row(_("Query Level:"), _("Stufe 2 (with name/address verification)")),
        html_row(_("Status:"), status_span, escape_value=False),
        html_row(_("Return Code:"), str(result.return_code)),
        html_row(_("Message:"), result.message),
        html_row(_("Severity:"), severity_span, escape_value=False),
        html_row(_("Retryable:"), _("Yes") if info.retryable else _("No")),
        html_row(_("Timestamp:"), format_local_time(result.timestamp)),
    ]
    return "".join(rows) + _format_company_section_html(result)


def format_result_html(result: "UidCheckResult") -> str:
    """Format UID check result as HTML document.

    Produces a complete, styled HTML document suitable for saving
    to file, viewing in a browser, printing, or embedding in emails.

    Args:
        result: UID verification result to format.

    Returns:
        Complete HTML document string.

    Examples:
        >>> from datetime import datetime, timezone
        >>> from finanzonline_uid.domain.models import UidCheckResult
        >>> result = UidCheckResult(
        ...     uid="DE123456789",
        ...     return_code=0,
        ...     message="UID is valid",
        ...     timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ... )
        >>> output = format_result_html(result)
        >>> "DE123456789" in output
        True
        >>> "<!DOCTYPE html>" in output
        True
    """
    info = get_return_code_info(result.return_code)
    rows = _build_result_table_rows(result, info)
    cache_notice = _format_cache_notice_html(result)
    title = _("UID Verification Result (Stufe 2)")
    return f'{HTML_DOCTYPE.format(title=title)}<body style="{HTML_BODY_STYLE}"><h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">{title}</h2><table style="{HTML_TABLE_STYLE}">{rows}</table>{cache_notice}{get_html_footer()}</body></html>'
