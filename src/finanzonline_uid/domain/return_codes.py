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

from dataclasses import dataclass
from enum import Enum, IntEnum

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


# Return code mappings from BMF documentation
# Strings are marked with N_() for extraction and translated at runtime in get_return_code_info()
_RETURN_CODE_INFO: dict[int, ReturnCodeInfo] = {
    # Success
    0: ReturnCodeInfo(code=0, meaning=N_("UID is valid"), severity=Severity.SUCCESS),
    # UID Status
    1: ReturnCodeInfo(code=1, meaning=N_("UID is invalid"), severity=Severity.WARNING),
    # Session/Auth errors
    -1: ReturnCodeInfo(code=-1, meaning=N_("Session invalid or expired"), severity=Severity.ERROR),
    -2: ReturnCodeInfo(code=-2, meaning=N_("System maintenance"), severity=Severity.WARNING, retryable=True),
    -3: ReturnCodeInfo(code=-3, meaning=N_("Technical error"), severity=Severity.ERROR, retryable=True),
    -4: ReturnCodeInfo(code=-4, meaning=N_("The access codes are not valid"), severity=Severity.CRITICAL),
    -5: ReturnCodeInfo(code=-5, meaning=N_("User locked due to incorrect login attempts"), severity=Severity.CRITICAL),
    -6: ReturnCodeInfo(code=-6, meaning=N_("User is locked"), severity=Severity.CRITICAL),
    -7: ReturnCodeInfo(code=-7, meaning=N_("User is not a web service user"), severity=Severity.CRITICAL),
    -8: ReturnCodeInfo(code=-8, meaning=N_("Participant locked or not authorized for web service"), severity=Severity.CRITICAL),
    # Query parameter errors
    4: ReturnCodeInfo(code=4, meaning=N_("Wrong UID format"), severity=Severity.ERROR),
    5: ReturnCodeInfo(code=5, meaning=N_("Invalid requester UID"), severity=Severity.ERROR),
    # Query restrictions
    10: ReturnCodeInfo(code=10, meaning=N_("Member state forbids query"), severity=Severity.WARNING),
    11: ReturnCodeInfo(code=11, meaning=N_("Not authorized for requester UID"), severity=Severity.ERROR),
    12: ReturnCodeInfo(code=12, meaning=N_("UID not yet queryable"), severity=Severity.WARNING, retryable=True),
    # Special cases
    101: ReturnCodeInfo(code=101, meaning=N_("UID doesn't start with ATU"), severity=Severity.ERROR),
    103: ReturnCodeInfo(code=103, meaning=N_("VAT group (CZ) - special handling required"), severity=Severity.WARNING),
    104: ReturnCodeInfo(code=104, meaning=N_("VAT group (SK) - special handling required"), severity=Severity.WARNING),
    105: ReturnCodeInfo(code=105, meaning=N_("Must query via FinanzOnline portal directly"), severity=Severity.ERROR),
    # Service errors
    1511: ReturnCodeInfo(code=1511, meaning=N_("Service unavailable"), severity=Severity.CRITICAL, retryable=True),
    1512: ReturnCodeInfo(code=1512, meaning=N_("Too many queries (server load)"), severity=Severity.WARNING, retryable=True),
    1513: ReturnCodeInfo(code=1513, meaning=N_("Rate limit: 2 queries per UID per day exceeded"), severity=Severity.WARNING, retryable=True),
    1514: ReturnCodeInfo(code=1514, meaning=N_("Rate limit: requester limit exceeded"), severity=Severity.WARNING, retryable=True),
}


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
    if code in _RETURN_CODE_INFO:
        info = _RETURN_CODE_INFO[code]
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
