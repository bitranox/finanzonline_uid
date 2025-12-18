"""Output formatters for CLI display.

Purpose
-------
Transform UID verification results into formatted output for
console display in either human-readable or JSON format.

Contents
--------
* :func:`format_human` - Human-readable console output
* :func:`format_json` - JSON structured output

System Role
-----------
Adapters layer - transforms domain models into CLI output strings.

Examples
--------
>>> from datetime import datetime, timezone
>>> from uid_check_austria.domain.models import UidCheckResult
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

from uid_check_austria._datetime_utils import format_local_time
from uid_check_austria.domain.return_codes import ReturnCodeInfo, get_return_code_info
from uid_check_austria.i18n import _

if TYPE_CHECKING:
    from uid_check_austria.domain.models import UidCheckResult


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
    color = severity_colors.get(info.severity.value, _RESET)
    return f"{color}{info.severity.value.upper()}{_RESET}"


def _format_address_lines(address_lines: list[str]) -> list[str]:
    """Format address lines with proper indentation."""
    if not address_lines:
        return []
    label = _("Address:")
    padding = " " * len(label)
    return [f"{label} {address_lines[0]}"] + [f"{padding} {line}" for line in address_lines[1:]]


def _format_company_section(result: UidCheckResult) -> list[str]:
    """Format company information section if available."""
    if not (result.is_valid and result.name):
        return []

    lines = ["", f"{_BOLD}{_('Company Information')}{_RESET}", "-" * 30, f"{_('Name:')}    {result.name}"]
    if result.address:
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
        >>> from uid_check_austria.domain.models import UidCheckResult
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
        >>> from uid_check_austria.domain.models import UidCheckResult
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
        "severity": info.severity.value,
        "retryable": info.retryable,
        "timestamp": result.timestamp.isoformat(),
    }

    if result.name:
        company: dict[str, Any] = {"name": result.name}
        if result.address:
            company["address"] = {
                "lines": result.address.as_lines(),
                "text": result.address.as_text(),
            }
        data["company"] = company

    return json.dumps(data, indent=2)
