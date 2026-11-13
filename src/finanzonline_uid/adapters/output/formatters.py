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
* :func:`format_command_error_json` - JSON error output of a command without a UID

System Role
-----------
Adapters layer - transforms domain models into CLI output strings.
The JSON outputs are built from the private ``_*Out`` models below and
serialized with the same ``json.dumps`` call as always, so the wire stays
byte-identical.

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
from collections.abc import Mapping
from datetime import datetime, timezone
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from pydantic import BaseModel, ConfigDict

from finanzonline_uid._datetime_utils import format_local_time
from finanzonline_uid.adapters.formatting import format_result_html
from finanzonline_uid.adapters.formatting.html_templates import ResultStatus, classify_result, result_status_label
from finanzonline_uid.domain.errors import ErrorKind
from finanzonline_uid.domain.models import SoapOperation
from finanzonline_uid.domain.return_codes import ReturnCodeInfo, Severity, get_return_code_info
from finanzonline_uid.i18n import _

if TYPE_CHECKING:
    from finanzonline_uid.domain.errors import CheckErrorInfo
    from finanzonline_uid.domain.models import Diagnostics, UidCheckResult

__all__ = [
    "format_command_error_json",
    "format_error_human",
    "format_error_json",
    "format_html",
    "format_human",
    "format_json",
]


# ANSI color constants
_RESET = "\033[0m"
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"

SEVERITY_ANSI_COLORS: Final[Mapping[Severity, str]] = MappingProxyType(
    {
        Severity.SUCCESS: _GREEN,
        Severity.WARNING: _YELLOW,
        Severity.ERROR: _RED,
        Severity.CRITICAL: _RED,
    }
)

# Console colour per result status. The status itself comes from classify_result,
# the same classification the HTML and email output use, so the three cannot
# disagree about a code. Every non-valid, non-invalid status keeps the yellow the
# console has always used for them.
STATUS_ANSI_COLORS: Final[Mapping[ResultStatus, str]] = MappingProxyType(
    {
        ResultStatus.VALID: _GREEN,
        ResultStatus.INVALID: _RED,
        ResultStatus.UNAVAILABLE: _YELLOW,
        ResultStatus.RATE_LIMITED: _YELLOW,
        ResultStatus.ERROR: _YELLOW,
    }
)


class _AddressOut(BaseModel):
    """The ``company.address`` object of the result JSON."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lines: list[str]
    text: str


class _CompanyOut(BaseModel):
    """The ``company`` object of the result JSON; an absent part is omitted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str | None = None
    address: _AddressOut | None = None


class _ResultOut(BaseModel):
    """The result JSON printed by ``check --format json``.

    Field order is the key order on the wire. ``None`` marks a key that is
    left out, which is why the dump uses ``exclude_none``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    uid: str
    is_valid: bool
    return_code: int
    message: str
    severity: Severity
    retryable: bool
    # A preformatted string, not a datetime: pydantic would write a UTC offset
    # as "Z", while the wire has always carried isoformat()'s "+00:00".
    timestamp: str
    company: _CompanyOut | None = None


class _DiagnosticsOut(BaseModel):
    """The ``diagnostics`` object of the error JSON.

    One field per :class:`~finanzonline_uid.domain.models.DiagnosticField`
    value, in display order, followed by ``raw_response``. An empty value is
    ``None`` and omitted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: SoapOperation | None = None
    tid: str | None = None
    benid: str | None = None
    pin: str | None = None
    uid_tn: str | None = None
    target_uid: str | None = None
    session_id: str | None = None
    return_code: str | None = None
    response_message: str | None = None
    error_detail: str | None = None
    raw_response: str | None = None


class _ErrorOut(BaseModel):
    """The error JSON printed by ``check --format json`` when a check fails.

    The return-code fields and ``diagnostics`` are ``None`` (omitted) when
    the failure carries no return code or no diagnostics.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    uid: str
    is_valid: bool = False
    error: bool = True
    error_type: ErrorKind
    message: str
    retryable: bool
    timestamp: str
    return_code: int | None = None
    meaning: str | None = None
    severity: Severity | None = None
    diagnostics: _DiagnosticsOut | None = None


class _CommandErrorOut(BaseModel):
    """The error JSON of a command that checks no UID (``config --format json``).

    Its fields carry the same names, types and meaning as the matching
    fields of :class:`_ErrorOut`, so a caller reads both records with one
    rule; every field about a UID or a FinanzOnline reply is left out.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    error: bool = True
    error_type: ErrorKind
    message: str
    timestamp: str


def _dump_json(model: BaseModel) -> str:
    """Serialize an output model with the JSON call the CLI has always used."""
    return json.dumps(model.model_dump(mode="json", exclude_none=True), indent=2)


def _get_status_display(result: UidCheckResult) -> str:
    """Get the colored status label of a result.

    The label is the translated text the HTML badge and the email show.
    """
    status = classify_result(result.return_code)
    return f"{STATUS_ANSI_COLORS[status]}{_BOLD}{result_status_label(status)}{_RESET}"


def _get_severity_display(info: ReturnCodeInfo) -> str:
    """Get colored severity display string."""
    return f"{SEVERITY_ANSI_COLORS[info.severity]}{info.severity.value.upper()}{_RESET}"


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


def _company_out(result: UidCheckResult) -> _CompanyOut | None:
    """Build the ``company`` object, or None when the result has no company data."""
    if not result.has_company_info:
        return None
    address = result.address
    address_out = None
    if address is not None and not address.is_empty:
        address_out = _AddressOut(lines=address.as_lines(), text=address.as_text())
    return _CompanyOut(name=result.name or None, address=address_out)


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
    out = _ResultOut(
        uid=result.uid,
        is_valid=result.is_valid,
        return_code=result.return_code,
        message=result.message,
        severity=info.severity,
        retryable=info.retryable,
        timestamp=result.timestamp.isoformat(),
        company=_company_out(result),
    )
    return _dump_json(out)


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
    return format_result_html(result)


def _format_diagnostics_section(diagnostics: Diagnostics) -> list[str]:
    """Format diagnostics section for human-readable output."""
    lines = ["", f"{_BOLD}{_('Diagnostic Information')}{_RESET}", "-" * 30]
    lines.extend(f"{entry.field.label}: {entry.value}" for entry in diagnostics.entries())
    if diagnostics.raw_response:
        lines.extend(["", f"{_BOLD}{_('Raw SOAP Response')}{_RESET}", "-" * 30, diagnostics.raw_response])
    return lines


def format_error_human(info: CheckErrorInfo, uid: str) -> str:
    """Format error as human-readable text for CLI display.

    Produces colored console output suitable for terminal display.
    Uses ANSI escape codes for color highlighting.

    Args:
        info: The failure to report: kind, message, return code,
            retryability and diagnostics.
        uid: The UID that was being checked.

    Returns:
        Formatted string for console output.
    """
    lines = [
        f"{_RED}{_BOLD}{_('UID Check ERROR')}{_RESET}",
        "=" * 40,
        f"{_('UID:')}         {uid}",
        f"{_('Status:')}      {_RED}{_BOLD}{_('ERROR')}{_RESET}",
        f"{_('Error Type:')}  {_RED}{info.error_type.value}{_RESET}",
        f"{_('Message:')}     {info.message}",
    ]

    if info.return_code is not None:
        code_info = get_return_code_info(info.return_code)
        lines.extend(
            [
                f"{_('Return Code:')} {info.return_code}",
                f"{_('Meaning:')}     {code_info.meaning}",
                f"{_('Severity:')}    {_get_severity_display(code_info)}",
            ]
        )

    lines.extend(
        [
            f"{_('Retryable:')}   {_('Yes') if info.retryable else _('No')}",
            f"{_('Timestamp:')}   {format_local_time(datetime.now(timezone.utc))}",
        ]
    )

    if info.diagnostics and not info.diagnostics.is_empty:
        lines.extend(_format_diagnostics_section(info.diagnostics))

    return "\n".join(lines)


def _diagnostics_out(diagnostics: Diagnostics | None) -> _DiagnosticsOut | None:
    """Build the ``diagnostics`` object, or None when there is nothing to show."""
    if diagnostics is None or diagnostics.is_empty:
        return None
    # Keyword arguments rather than a dict built from entries(), so the type
    # checker sees every field mapping. An empty string becomes None, which the
    # dump omits, exactly as entries() skips empty fields.
    return _DiagnosticsOut(
        operation=diagnostics.operation,
        tid=diagnostics.tid or None,
        benid=diagnostics.benid or None,
        pin=diagnostics.pin or None,
        uid_tn=diagnostics.uid_tn or None,
        target_uid=diagnostics.target_uid or None,
        session_id=diagnostics.session_id or None,
        return_code=diagnostics.return_code or None,
        response_message=diagnostics.response_message or None,
        error_detail=diagnostics.error_detail or None,
        raw_response=diagnostics.raw_response or None,
    )


def format_error_json(info: CheckErrorInfo, uid: str) -> str:
    """Format error as JSON for CLI display.

    Produces structured JSON output suitable for programmatic
    consumption and piping to other tools.

    Args:
        info: The failure to report: kind, message, return code,
            retryability and diagnostics.
        uid: The UID that was being checked.

    Returns:
        JSON string representation.
    """
    code_info = get_return_code_info(info.return_code) if info.return_code is not None else None
    out = _ErrorOut(
        uid=uid,
        error_type=info.error_type,
        message=info.message,
        retryable=info.retryable,
        timestamp=datetime.now(timezone.utc).isoformat(),
        return_code=info.return_code,
        meaning=code_info.meaning if code_info is not None else None,
        severity=code_info.severity if code_info is not None else None,
        diagnostics=_diagnostics_out(info.diagnostics),
    )
    return _dump_json(out)


def format_command_error_json(error_type: ErrorKind, message: str) -> str:
    """Format the error of a command that checks no UID as JSON.

    Args:
        error_type: Category of the failure; its value is the ``error_type``.
        message: Human-readable error description.

    Returns:
        JSON string with ``error``, ``error_type``, ``message`` and ``timestamp``.

    Examples:
        >>> record = json.loads(format_command_error_json(ErrorKind.VALIDATION, "Section 'x' not found or empty"))
        >>> sorted(record), record["error_type"]
        (['error', 'error_type', 'message', 'timestamp'], 'Validation Error')
    """
    out = _CommandErrorOut(error_type=error_type, message=message, timestamp=datetime.now(timezone.utc).isoformat())
    return _dump_json(out)
