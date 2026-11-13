"""HTML error formatter for email notifications.

Purpose
-------
Format error notifications as HTML for email delivery.

Contents
--------
* :func:`format_error_html` - HTML error formatter

System Role
-----------
Adapters layer - HTML email body formatting for errors.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from finanzonline_uid._datetime_utils import format_local_time
from finanzonline_uid.adapters.formatting.html_templates import (
    HTML_BODY_STYLE,
    HTML_DOCTYPE,
    HTML_TABLE_STYLE,
    html_row,
)
from finanzonline_uid.domain.return_codes import get_return_code_info
from finanzonline_uid.i18n import _

if TYPE_CHECKING:
    from finanzonline_uid.domain.errors import CheckErrorInfo
    from finanzonline_uid.domain.models import Diagnostics

__all__ = ["format_error_html"]


def _format_return_code_section_html(return_code: int) -> str:
    """Format return code section as HTML table rows."""
    info = get_return_code_info(return_code)
    return f"""
        <tr><td style="padding: 8px 15px; font-weight: bold;">{_("Return Code:")}</td><td style="padding: 8px 15px;">{return_code}</td></tr>
        <tr><td style="padding: 8px 15px; font-weight: bold;">{_("Meaning:")}</td><td style="padding: 8px 15px;">{html.escape(info.meaning)}</td></tr>
        <tr><td style="padding: 8px 15px; font-weight: bold;">{_("Severity:")}</td><td style="padding: 8px 15px;"><span style="color: #dc3545; font-weight: bold;">{html.escape(info.severity.value.upper())}</span></td></tr>"""


def _format_raw_response_block_html(raw_response: str) -> str:
    """Format raw SOAP response as a preformatted HTML code block."""
    if not raw_response:
        return ""
    escaped = html.escape(raw_response)
    return (
        f'<h3 style="color: #856404; border-bottom: 1px solid #ffc107; padding-bottom: 8px; margin-top: 30px;">{_("Raw SOAP Response")}</h3>'
        f'<pre style="background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 12px; '
        f"font-family: monospace; font-size: 0.8em; white-space: pre-wrap; word-break: break-all; "
        f'overflow-x: auto; max-height: 400px;">{escaped}</pre>'
    )


def _format_diagnostics_section_html(diagnostics: Diagnostics) -> str:
    """Format diagnostics section as HTML."""
    rows = "".join(
        f'<tr><td style="padding: 6px 15px; font-weight: bold; color: #666; font-size: 0.9em;">{html.escape(entry.field.label)}:</td>'
        f'<td style="padding: 6px 15px; font-family: monospace; font-size: 0.85em; word-break: break-all;">{html.escape(entry.value)}</td></tr>'
        for entry in diagnostics.entries()
    )
    table = (
        f'<h3 style="color: #856404; border-bottom: 1px solid #ffc107; padding-bottom: 8px; margin-top: 30px;">{_("Diagnostic Information")}</h3>'
        f'<table style="width: 100%; border-collapse: collapse; margin: 10px 0; background-color: #fff3cd; border-radius: 4px;">{rows}</table>'
    )
    return table + _format_raw_response_block_html(diagnostics.raw_response)


def _build_error_table_rows(info: CheckErrorInfo, uid: str, timestamp: str) -> str:
    """Build HTML table rows for error display."""
    error_span = (
        f'<span style="background-color: #dc3545; color: white; padding: 4px 12px; border-radius: 4px; font-weight: bold;">{html.escape(_("ERROR"))}</span>'
    )
    rows = [
        html_row(_("UID:"), uid, " font-family: monospace; font-size: 1.1em;"),
        html_row(_("Status:"), error_span, escape_value=False),
        html_row(_("Error Type:"), info.error_type.value, " color: #dc3545; font-weight: bold;"),
        html_row(_("Message:"), info.message),
    ]
    if info.return_code is not None:
        rows.append(_format_return_code_section_html(info.return_code))
    rows.extend(
        [
            html_row(_("Retryable:"), _("Yes - try again later") if info.retryable else _("No")),
            html_row(_("Timestamp:"), timestamp),
        ]
    )
    return "".join(rows)


def format_error_html(info: CheckErrorInfo, uid: str) -> str:
    """Format error notification as HTML.

    Args:
        info: The failure to report: kind, message, return code,
            retryability and diagnostics.
        uid: The UID that was being checked.

    Returns:
        HTML error notification.
    """
    timestamp = format_local_time(datetime.now(timezone.utc))
    rows = _build_error_table_rows(info, uid, timestamp)
    diagnostics = info.diagnostics
    diag_section = _format_diagnostics_section_html(diagnostics) if diagnostics and not diagnostics.is_empty else ""
    title = _("UID Check Error")
    header = _("UID Check ERROR")
    footer = f'<p style="color: #7f8c8d; font-size: 0.9em; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px;">{_("This is an automated error notification from finanzonline-uid.")}</p>'
    return f'{HTML_DOCTYPE.format(title=title)}<body style="{HTML_BODY_STYLE}"><h2 style="color: #dc3545; border-bottom: 2px solid #dc3545; padding-bottom: 10px;">{header}</h2><table style="{HTML_TABLE_STYLE}">{rows}</table>{diag_section}{footer}</body></html>'
