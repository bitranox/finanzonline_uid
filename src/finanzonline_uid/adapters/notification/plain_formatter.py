"""Plain text formatters for email notifications.

Purpose
-------
Format UID verification results and errors as plain text for email
notifications.

Contents
--------
* :func:`format_result_plain` - Plain text result formatter
* :func:`format_error_plain` - Plain text error formatter

System Role
-----------
Adapters layer - plain text email body formatting.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from finanzonline_uid._datetime_utils import format_local_time
from finanzonline_uid.adapters.formatting.html_templates import get_result_status
from finanzonline_uid.domain.return_codes import get_return_code_info
from finanzonline_uid.i18n import _

if TYPE_CHECKING:
    from finanzonline_uid.domain.models import Address, Diagnostics, UidCheckResult


def _format_address_plain(address: Address) -> list[str]:
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
    status = get_result_status(result.return_code)

    lines = [
        _("UID Verification Result (Stufe 2)"),
        "=" * 50,
        "",
        f"{_('UID:')}         {result.uid}",
        _("Query Level: Stufe 2 (with name/address verification)"),
        f"{_('Status:')}      {status}",
        f"{_('Return Code:')} {result.return_code}",
        f"{_('Message:')}     {result.message}",
        f"{_('Severity:')}    {info.severity}",
        f"{_('Retryable:')}   {_('Yes') if info.retryable else _('No')}",
        f"{_('Timestamp:')}   {format_local_time(result.timestamp)}",
    ]

    lines.extend(_format_company_section_plain(result))
    lines.extend(_format_cache_notice_plain(result))
    lines.extend(["", "-" * 50, _("This is an automated message from finanzonline-uid.")])

    return "\n".join(lines)


def _format_return_code_section_plain(return_code: int) -> list[str]:
    """Format return code section for plain text error output."""
    info = get_return_code_info(return_code)
    return [f"{_('Return Code:')} {return_code}", f"{_('Meaning:')}     {info.meaning}", f"{_('Severity:')}    {info.severity}"]


def _format_diagnostics_section_plain(diagnostics: Diagnostics) -> list[str]:
    """Format diagnostics section for plain text error output."""
    lines = ["", _("Diagnostic Information"), "-" * 30]
    for key, value in diagnostics.as_dict().items():
        lines.append(f"{key.replace('_', ' ').title()}: {value}")
    if diagnostics.raw_response:
        lines.extend(["", _("Raw SOAP Response"), "-" * 30, diagnostics.raw_response])
    return lines


def format_error_plain(
    error_type: str,
    error_message: str,
    uid: str,
    return_code: int | None = None,
    retryable: bool = False,
    diagnostics: Diagnostics | None = None,
) -> str:
    """Format error notification as plain text.

    Args:
        error_type: Type of error (e.g., "Authentication Error").
        error_message: Error message details.
        uid: The UID that was being checked.
        return_code: Optional return code from BMF.
        retryable: Whether the error is retryable.
        diagnostics: Optional Diagnostics object for debugging.

    Returns:
        Plain text error notification.
    """
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

    lines.extend(["", "-" * 50, _("This is an automated error notification from finanzonline-uid.")])
    return "\n".join(lines)
