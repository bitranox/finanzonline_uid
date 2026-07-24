"""Output formatters for CLI display.

Purpose
-------
Transform UID verification results into formatted output for
console display in either human-readable, JSON, or HTML format.

Contents
--------
* :func:`format_human` - Human-readable console output
* :func:`format_json` - JSON structured output
* :func:`format_html` - HTML document output
* :func:`format_error_human` - Human-readable error output
* :func:`format_error_json` - JSON error output

System Role
-----------
Adapters layer - transforms domain models into CLI output strings.

Examples
--------
>>> from datetime import datetime, timezone
>>> from finanzonline_uid.domain.models import UidCheckResult
>>> result = UidCheckResult(
...     uid="DE123456789",
...     return_code=0,
...     message="UID is valid",
...     timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
... )
>>> output = format_human(result)
>>> "DE123456789" in output
True
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from finanzonline_uid._datetime_utils import format_local_time
from finanzonline_uid.domain.return_codes import ReturnCodeInfo, get_return_code_info
from finanzonline_uid.i18n import _

if TYPE_CHECKING:
    from finanzonline_uid.domain.models import Diagnostics, UidCheckResult


# ANSI color constants
_RESET = "\033[0m"
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"


def _get_status_display(result: UidCheckResult) -> str:
    """Get colored status display string."""
    if result.is_valid:
        return f"{_GREEN}{_BOLD}{_('VALID')}{_RESET}"
    if result.is_invalid:
        return f"{_RED}{_BOLD}{_('INVALID')}{_RESET}"
    return f"{_YELLOW}{_BOLD}{_('ERROR')}{_RESET}"


def _get_severity_display(info: ReturnCodeInfo) -> str:
    """Get colored severity display string."""
    severity_colors = {"success": _GREEN, "warning": _YELLOW, "error": _RED, "critical": _RED}
    color = severity_colors.get(info.severity, _RESET)
    return f"{color}{info.severity.upper()}{_RESET}"


def _format_address_lines(address_lines: list[str]) -> list[str]:
    """Format address lines with proper indentation."""
    if not address_lines:
        return []
    label = _("Address:")
    padding = " " * len(label)
    return [f"{label} {address_lines[0]}"] + [f"{padding} {line}" for line in address_lines[1:]]


def _format_company_section(result: UidCheckResult) -> list[str]:
    """Format company information section if available."""
    if not result.has_company_info:
        return []

    lines = ["", f"{_BOLD}{_('Company Information')}{_RESET}", "-" * 30]
    if result.name:
        lines.append(f"{_('Name:')}    {result.name}")
    if result.address and not result.address.is_empty:
        lines.extend(_format_address_lines(result.address.as_lines()))
    return lines


def format_human(result: UidCheckResult) -> str:
    """Format UID check result as human-readable text.

    Produces colored console output suitable for terminal display.
    Uses ANSI escape codes for color highlighting.

    Args:
        result: UID verification result to format.

    Returns:
        Formatted string for console output.

    Examples:
        >>> from datetime import datetime, timezone
        >>> from finanzonline_uid.domain.models import UidCheckResult
        >>> result = UidCheckResult(
        ...     uid="DE123456789",
        ...     return_code=0,
        ...     message="UID is valid",
        ...     timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ... )
        >>> output = format_human(result)
        >>> "DE123456789" in output
        True
    """
    info = get_return_code_info(result.return_code)

    lines = [
        f"{_BOLD}{_('UID Check Result')}{_RESET}",
        "=" * 40,
        f"{_('UID:')}         {result.uid}",
        f"{_('Status:')}      {_get_status_display(result)}",
        f"{_('Return Code:')} {result.return_code}",
        f"{_('Message:')}     {result.message}",
        f"{_('Severity:')}    {_get_severity_display(info)}",
        f"{_('Retryable:')}   {_('Yes') if info.retryable else _('No')}",
        f"{_('Timestamp:')}   {format_local_time(result.timestamp)}",
    ]

    lines.extend(_format_company_section(result))

    return "\n".join(lines)


def format_json(result: UidCheckResult) -> str:
    """Format UID check result as JSON.

    Produces structured JSON output suitable for programmatic
    consumption and piping to other tools.

    Args:
        result: UID verification result to format.

    Returns:
        JSON string representation.

    Examples:
        >>> from datetime import datetime, timezone
        >>> from finanzonline_uid.domain.models import UidCheckResult
        >>> result = UidCheckResult(
        ...     uid="DE123456789",
        ...     return_code=0,
        ...     message="UID is valid",
        ...     timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ... )
        >>> output = format_json(result)
        >>> import json
        >>> data = json.loads(output)
        >>> data["uid"]
        'DE123456789'
    """
    info = get_return_code_info(result.return_code)

    data: dict[str, Any] = {
        "uid": result.uid,
        "is_valid": result.is_valid,
        "return_code": result.return_code,
        "message": result.message,
        "severity": info.severity,
        "retryable": info.retryable,
        "timestamp": result.timestamp.isoformat(),
    }

    if result.has_company_info:
        company: dict[str, Any] = {}
        if result.name:
            company["name"] = result.name
        if result.address and not result.address.is_empty:
            company["address"] = {
                "lines": result.address.as_lines(),
                "text": result.address.as_text(),
            }
        data["company"] = company

    return json.dumps(data, indent=2)


def format_html(result: UidCheckResult) -> str:
    """Format UID check result as HTML document.

    Produces a complete, styled HTML document suitable for saving
    to file, viewing in a browser, or printing.

    Args:
        result: UID verification result to format.

    Returns:
        HTML document string.

    Examples:
        >>> from datetime import datetime, timezone
        >>> from finanzonline_uid.domain.models import UidCheckResult
        >>> result = UidCheckResult(
        ...     uid="DE123456789",
        ...     return_code=0,
        ...     message="UID is valid",
        ...     timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ... )
        >>> output = format_html(result)
        >>> "DE123456789" in output
        True
        >>> "<!DOCTYPE html>" in output
        True
    """
    from finanzonline_uid.adapters.formatting import format_result_html

    return format_result_html(result)


def _format_diagnostics_section(diagnostics: Diagnostics) -> list[str]:
    """Format diagnostics section for human-readable output."""
    lines = ["", f"{_BOLD}{_('Diagnostic Information')}{_RESET}", "-" * 30]
    for key, value in diagnostics.as_dict().items():
        lines.append(f"{key.replace('_', ' ').title()}: {value}")
    if diagnostics.raw_response:
        lines.extend(["", f"{_BOLD}{_('Raw SOAP Response')}{_RESET}", "-" * 30, diagnostics.raw_response])
    return lines


def format_error_human(
    error_type: str,
    error_message: str,
    uid: str,
    return_code: int | None = None,
    retryable: bool = False,
    diagnostics: Diagnostics | None = None,
) -> str:
    """Format error as human-readable text for CLI display.

    Produces colored console output suitable for terminal display.
    Uses ANSI escape codes for color highlighting.

    Args:
        error_type: Type of error (e.g., "Authentication Error").
        error_message: Error message details.
        uid: The UID that was being checked.
        return_code: Optional return code from BMF.
        retryable: Whether the error is retryable.
        diagnostics: Optional Diagnostics object for debugging.

    Returns:
        Formatted string for console output.
    """
    from datetime import datetime, timezone

    lines = [
        f"{_RED}{_BOLD}{_('UID Check ERROR')}{_RESET}",
        "=" * 40,
        f"{_('UID:')}         {uid}",
        f"{_('Status:')}      {_RED}{_BOLD}{_('ERROR')}{_RESET}",
        f"{_('Error Type:')}  {_RED}{error_type}{_RESET}",
        f"{_('Message:')}     {error_message}",
    ]

    if return_code is not None:
        info = get_return_code_info(return_code)
        lines.extend(
            [
                f"{_('Return Code:')} {return_code}",
                f"{_('Meaning:')}     {info.meaning}",
                f"{_('Severity:')}    {_get_severity_display(info)}",
            ]
        )

    lines.extend(
        [
            f"{_('Retryable:')}   {_('Yes') if retryable else _('No')}",
            f"{_('Timestamp:')}   {format_local_time(datetime.now(timezone.utc))}",
        ]
    )

    if diagnostics and not diagnostics.is_empty:
        lines.extend(_format_diagnostics_section(diagnostics))

    return "\n".join(lines)


def format_error_json(
    error_type: str,
    error_message: str,
    uid: str,
    return_code: int | None = None,
    retryable: bool = False,
    diagnostics: Diagnostics | None = None,
) -> str:
    """Format error as JSON for CLI display.

    Produces structured JSON output suitable for programmatic
    consumption and piping to other tools.

    Args:
        error_type: Type of error (e.g., "Authentication Error").
        error_message: Error message details.
        uid: The UID that was being checked.
        return_code: Optional return code from BMF.
        retryable: Whether the error is retryable.
        diagnostics: Optional Diagnostics object for debugging.

    Returns:
        JSON string representation.
    """
    from datetime import datetime, timezone

    data: dict[str, Any] = {
        "uid": uid,
        "is_valid": False,
        "error": True,
        "error_type": error_type,
        "message": error_message,
        "retryable": retryable,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if return_code is not None:
        info = get_return_code_info(return_code)
        data["return_code"] = return_code
        data["meaning"] = info.meaning
        data["severity"] = info.severity

    if diagnostics and not diagnostics.is_empty:
        diag_dict: dict[str, Any] = dict(diagnostics.as_dict())
        if diagnostics.raw_response:
            diag_dict["raw_response"] = diagnostics.raw_response
        data["diagnostics"] = diag_dict

    return json.dumps(data, indent=2)
