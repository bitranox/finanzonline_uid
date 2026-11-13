"""FinanzOnline return code definitions.

Purpose
-------
Define return codes from BMF FinanzOnline UID query webservice with
severity classification and human-readable descriptions.

Contents
--------
* :class:`Severity` - Error severity levels
* :class:`ReturnCode` - Enumeration of known return codes
* :class:`ReturnCodeInfo` - Metadata for a return code
* :func:`get_return_code_info` - Lookup return code information

System Role
-----------
Domain layer - pure data definitions based on BMF documentation.
Used by application layer to interpret query results.

Reference
---------
BMF UID-Abfrage Webservice documentation (BMF_UID_Abfrage_Webservice_2.pdf)

Examples
--------
>>> info = get_return_code_info(0)
>>> info.meaning  # doctest: +SKIP
'UID is valid'
>>> info.severity
<Severity.SUCCESS: 'success'>

>>> info = get_return_code_info(1513)
>>> info.retryable
True
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, IntEnum
from types import MappingProxyType
from typing import Final

from finanzonline_uid.i18n import N_, _


class CliExitCode(IntEnum):
    """CLI exit codes for the check command.

    Standard exit codes used by the CLI to indicate result status.
    These are distinct from FinanzOnline return codes.

    Note: SUCCESS (0) is used for valid UIDs. UID_INVALID (1) for invalid UIDs.
    """

    SUCCESS = 0  # Also used when UID is valid
    UID_INVALID = 1
    CONFIG_ERROR = 2
    AUTH_ERROR = 3
    QUERY_ERROR = 4


class Severity(str, Enum):
    """Severity levels for return codes.

    Used to classify the nature of each return code for
    appropriate handling and user notification.
    Inherits from str for direct string comparison without .value access.
    """

    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ReturnCode(IntEnum):
    """Known FinanzOnline return codes.

    Values correspond to the 'rc' field in UID query responses.
    Inherits from IntEnum for direct integer comparison without .value access.
    """

    # Success
    UID_VALID = 0

    # UID Status
    UID_INVALID = 1

    # Session/Auth errors (negative codes)
    SESSION_INVALID = -1
    SYSTEM_MAINTENANCE = -2
    TECHNICAL_ERROR = -3
    NOT_AUTHORIZED = -4
    USER_LOCKED_LOGIN_ATTEMPTS = -5
    USER_LOCKED = -6
    NOT_WEBSERVICE_USER = -7
    PARTICIPANT_LOCKED = -8

    # Query parameter errors
    WRONG_UID_FORMAT = 4
    INVALID_REQUESTER_UID = 5

    # Query restrictions
    MEMBER_STATE_FORBIDS = 10
    NOT_AUTHORIZED_FOR_REQUESTER = 11
    UID_NOT_YET_QUERYABLE = 12

    # Special cases
    UID_NOT_STARTS_ATU = 101
    VAT_GROUP_CZ = 103
    VAT_GROUP_SK = 104
    MUST_QUERY_VIA_PORTAL = 105

    # Service errors
    SERVICE_UNAVAILABLE = 1511
    TOO_MANY_QUERIES_SERVER = 1512
    RATE_LIMIT_UID_EXCEEDED = 1513
    RATE_LIMIT_REQUESTER_EXCEEDED = 1514


@dataclass(frozen=True, slots=True)
class ReturnCodeInfo:
    """Metadata for a FinanzOnline return code.

    Attributes:
        code: Numeric return code.
        meaning: Human-readable description.
        severity: Error severity level.
        retryable: Whether the operation may succeed if retried later.
    """

    code: int
    meaning: str
    severity: Severity
    retryable: bool = False


def _entry(code: ReturnCode, meaning: str, severity: Severity, *, retryable: bool = False) -> tuple[ReturnCode, ReturnCodeInfo]:
    """Build one table row, so each code is named once and its info carries the plain int."""
    return code, ReturnCodeInfo(code=code.value, meaning=meaning, severity=severity, retryable=retryable)


# Return code mappings from BMF documentation; tests pin that every ReturnCode has a row.
# Strings are marked with N_() for extraction and translated at runtime in get_return_code_info()
_RETURN_CODE_INFO: Final[Mapping[ReturnCode, ReturnCodeInfo]] = MappingProxyType(
    dict(
        [
            # Success
            _entry(ReturnCode.UID_VALID, N_("UID is valid"), Severity.SUCCESS),
            # UID Status
            _entry(ReturnCode.UID_INVALID, N_("UID is invalid"), Severity.WARNING),
            # Session/Auth errors
            _entry(ReturnCode.SESSION_INVALID, N_("Session invalid or expired"), Severity.ERROR),
            _entry(ReturnCode.SYSTEM_MAINTENANCE, N_("System maintenance"), Severity.WARNING, retryable=True),
            _entry(ReturnCode.TECHNICAL_ERROR, N_("Technical error"), Severity.ERROR, retryable=True),
            _entry(ReturnCode.NOT_AUTHORIZED, N_("The access codes are not valid"), Severity.CRITICAL),
            _entry(ReturnCode.USER_LOCKED_LOGIN_ATTEMPTS, N_("User locked due to incorrect login attempts"), Severity.CRITICAL),
            _entry(ReturnCode.USER_LOCKED, N_("User is locked"), Severity.CRITICAL),
            _entry(ReturnCode.NOT_WEBSERVICE_USER, N_("User is not a web service user"), Severity.CRITICAL),
            _entry(ReturnCode.PARTICIPANT_LOCKED, N_("Participant locked or not authorized for web service"), Severity.CRITICAL),
            # Query parameter errors
            _entry(ReturnCode.WRONG_UID_FORMAT, N_("Wrong UID format"), Severity.ERROR),
            _entry(ReturnCode.INVALID_REQUESTER_UID, N_("Invalid requester UID"), Severity.ERROR),
            # Query restrictions
            _entry(ReturnCode.MEMBER_STATE_FORBIDS, N_("Member state forbids query"), Severity.WARNING),
            _entry(ReturnCode.NOT_AUTHORIZED_FOR_REQUESTER, N_("Not authorized for requester UID"), Severity.ERROR),
            _entry(ReturnCode.UID_NOT_YET_QUERYABLE, N_("UID not yet queryable"), Severity.WARNING, retryable=True),
            # Special cases
            _entry(ReturnCode.UID_NOT_STARTS_ATU, N_("UID doesn't start with ATU"), Severity.ERROR),
            _entry(ReturnCode.VAT_GROUP_CZ, N_("VAT group (CZ) - special handling required"), Severity.WARNING),
            _entry(ReturnCode.VAT_GROUP_SK, N_("VAT group (SK) - special handling required"), Severity.WARNING),
            _entry(ReturnCode.MUST_QUERY_VIA_PORTAL, N_("Must query via FinanzOnline portal directly"), Severity.ERROR),
            # Service errors
            _entry(ReturnCode.SERVICE_UNAVAILABLE, N_("Service unavailable"), Severity.CRITICAL, retryable=True),
            _entry(ReturnCode.TOO_MANY_QUERIES_SERVER, N_("Too many queries (server load)"), Severity.WARNING, retryable=True),
            _entry(ReturnCode.RATE_LIMIT_UID_EXCEEDED, N_("Rate limit: 2 queries per UID per day exceeded"), Severity.WARNING, retryable=True),
            _entry(ReturnCode.RATE_LIMIT_REQUESTER_EXCEEDED, N_("Rate limit: requester limit exceeded"), Severity.WARNING, retryable=True),
        ]
    )
)


def get_return_code_info(code: int) -> ReturnCodeInfo:
    """Get information about a return code.

    Args:
        code: Numeric return code from FinanzOnline response.

    Returns:
        ReturnCodeInfo with meaning, severity, and retryable flag.
        The meaning is translated to the current language.
        Returns a generic error info for unknown codes.

    Examples:
        >>> info = get_return_code_info(0)
        >>> info.meaning  # doctest: +SKIP
        'UID is valid'
        >>> info.severity == Severity.SUCCESS
        True

        >>> info = get_return_code_info(1513)
        >>> info.retryable
        True

        >>> info = get_return_code_info(9999)
        >>> _("Unknown return code") in info.meaning  # doctest: +SKIP
        True
    """
    try:
        info = _RETURN_CODE_INFO.get(ReturnCode(code))
    except ValueError:
        info = None
    if info is not None:
        # Translate meaning at runtime
        return ReturnCodeInfo(
            code=info.code,
            meaning=_(info.meaning),
            severity=info.severity,
            retryable=info.retryable,
        )

    # Translate unknown code message
    unknown_msg = _("Unknown return code")
    return ReturnCodeInfo(
        code=code,
        meaning=f"{unknown_msg}: {code}",
        severity=Severity.ERROR,
        retryable=False,
    )


def is_success(code: int) -> bool:
    """Check if return code indicates success.

    Args:
        code: Numeric return code.

    Returns:
        True if code is 0 (UID valid).

    Examples:
        >>> is_success(0)
        True
        >>> is_success(1)
        False
    """
    return code == ReturnCode.UID_VALID


def is_retryable(code: int) -> bool:
    """Check if operation with this return code may be retried.

    Args:
        code: Numeric return code.

    Returns:
        True if retry may succeed (e.g., temporary errors, rate limits).

    Examples:
        >>> is_retryable(1513)
        True
        >>> is_retryable(4)
        False
    """
    return get_return_code_info(code).retryable


__all__ = [
    "CliExitCode",
    "ReturnCode",
    "ReturnCodeInfo",
    "Severity",
    "get_return_code_info",
    "is_retryable",
    "is_success",
]
