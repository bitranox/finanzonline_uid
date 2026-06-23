"""Rate limit warning formatters for email notifications.

Purpose
-------
Format rate limit warning notifications as plain text and HTML
for email delivery.

Contents
--------
* :func:`format_rate_limit_warning_plain` - Plain text rate limit warning
* :func:`format_rate_limit_warning_html` - HTML rate limit warning

System Role
-----------
Adapters layer - rate limit warning email body formatting.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from finanzonline_uid._datetime_utils import format_local_time
from finanzonline_uid.adapters.formatting.html_templates import (
    HTML_BODY_STYLE,
    HTML_DOCTYPE,
    HTML_TABLE_STYLE,
    HTML_TD_STYLE,
)
from finanzonline_uid.i18n import _

if TYPE_CHECKING:
    from finanzonline_uid.adapters.ratelimit import RateLimitStatus


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
        _("This is an automated warning from finanzonline-uid."),
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
        <tr><td style="{HTML_TD_STYLE} font-weight: bold;">{_("Queries in window:")}</td><td style="{HTML_TD_STYLE}">{status.current_count}</td></tr>
        <tr><td style="{HTML_TD_STYLE} font-weight: bold;">{_("Maximum allowed:")}</td><td style="{HTML_TD_STYLE}">{status.max_queries}</td></tr>
        <tr><td style="{HTML_TD_STYLE} font-weight: bold;">{_("Window duration:")}</td><td style="{HTML_TD_STYLE}">{status.window_hours} {_("hours")}</td></tr>
        <tr><td style="{HTML_TD_STYLE} font-weight: bold;">{_("Timestamp:")}</td><td style="{HTML_TD_STYLE}">{timestamp}</td></tr>
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
    footer = f'<p style="color: #7f8c8d; font-size: 0.9em; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px;">{_("This is an automated warning from finanzonline-uid.")}</p>'

    return f"""{HTML_DOCTYPE.format(title=title)}
<body style="{HTML_BODY_STYLE}">
    <h2 style="color: #856404; border-bottom: 2px solid #ffc107; padding-bottom: 10px;">&#x26A0; {header}</h2>
    {warning_box}
    <h3 style="color: #333;">{_("Current Status")}</h3>
    <table style="{HTML_TABLE_STYLE}">{status_rows}</table>
    {policy_box}
    {important_box}
    <p style="color: #6c757d; font-size: 0.9em;">{note}</p>
    {footer}
</body>
</html>"""
