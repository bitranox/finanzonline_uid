"""Domain models for UID verification.

Purpose
-------
Immutable dataclasses representing core domain entities for FinanzOnline
UID verification. These models are pure value objects with no behavior
beyond basic property accessors.

Contents
--------
* :class:`Diagnostics` - Debug/diagnostic information for errors
* :class:`FinanzOnlineCredentials` - Authentication credentials
* :class:`SessionInfo` - Session state after login
* :class:`UidCheckRequest` - UID verification request parameters
* :class:`Address` - Company address (6 lines)
* :class:`UidCheckResult` - Complete verification result

System Role
-----------
Domain layer - pure data structures with no I/O dependencies. Used by
application layer use cases and passed through adapter boundaries.

Examples
--------
>>> creds = FinanzOnlineCredentials(
...     tid="123456789", benid="TESTUSER", pin="secretpin", herstellerid="ATU12345678"
... )
>>> creds.tid
'123456789'

>>> addr = Address(line1="Company GmbH", line2="Street 1", line3="1010 Vienna")
>>> addr.as_lines()
['Company GmbH', 'Street 1', '1010 Vienna']
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Well-known FinanzOnline return codes (avoids circular import with return_codes.py)
_RC_UID_VALID = 0
_RC_UID_INVALID = 1

# XSD validation patterns
_TID_PATTERN = re.compile(r"^[0-9A-Za-z]{8,12}$")
_BENID_MIN_LEN = 5
_BENID_MAX_LEN = 12
_PIN_MIN_LEN = 5
_PIN_MAX_LEN = 128
_HERSTELLERID_PATTERN = re.compile(r"^[0-9A-Za-z]{10,24}$")


def _validate_required(value: str, field_name: str, display_name: str) -> None:
    """Validate that a required field is not empty."""
    if not value:
        raise ValueError(f"{field_name} ({display_name}) is required")


def _validate_length_range(value: str, field_name: str, min_len: int, max_len: int) -> None:
    """Validate that a field length is within the specified range."""
    if not (min_len <= len(value) <= max_len):
        raise ValueError(f"{field_name} must be {min_len}-{max_len} characters, got {len(value)}")


def _validate_pattern(value: str, field_name: str, pattern: re.Pattern[str], description: str) -> None:
    """Validate that a field matches the specified pattern."""
    if not pattern.match(value):
        raise ValueError(f"{field_name} must be {description}, got: {value!r}")


@dataclass(frozen=True, slots=True)
class Diagnostics:
    """Debug/diagnostic information for error reporting.

    Captures request and response details for troubleshooting errors.
    All sensitive data (credentials) should be masked before storing.

    Attributes:
        operation: The operation being performed (e.g., 'login', 'query').
        tid: Masked participant ID (if applicable).
        benid: Masked user ID (if applicable).
        pin: Masked PIN/password (if applicable).
        uid_tn: Own Austrian UID (if applicable).
        target_uid: Target UID being queried (if applicable).
        session_id: Session ID (if applicable).
        return_code: Return code from response (if applicable).
        response_message: Response message from service (if applicable).
        error_detail: Additional error details (if applicable).

    Examples:
        >>> diag = Diagnostics(operation="login", tid="123***789", benid="TEST***", pin="sec***pin")
        >>> diag.as_dict()
        {'operation': 'login', 'tid': '123***789', 'benid': 'TEST***', 'pin': 'sec***pin'}
    """

    operation: str = ""
    tid: str = ""
    benid: str = ""
    pin: str = ""
    uid_tn: str = ""
    target_uid: str = ""
    session_id: str = ""
    return_code: str = ""
    response_message: str = ""
    error_detail: str = ""

    def as_dict(self) -> dict[str, str]:
        """Convert to dictionary, excluding empty values.

        Returns:
            Dictionary with only non-empty diagnostic values.
        """
        fields = [
            ("operation", self.operation),
            ("tid", self.tid),
            ("benid", self.benid),
            ("pin", self.pin),
            ("uid_tn", self.uid_tn),
            ("target_uid", self.target_uid),
            ("session_id", self.session_id),
            ("return_code", self.return_code),
            ("response_message", self.response_message),
            ("error_detail", self.error_detail),
        ]
        return {name: value for name, value in fields if value}

    @property
    def is_empty(self) -> bool:
        """Check if diagnostics contain no information."""
        return not any(
            [
                self.operation,
                self.tid,
                self.benid,
                self.pin,
                self.uid_tn,
                self.target_uid,
                self.session_id,
                self.return_code,
                self.response_message,
                self.error_detail,
            ]
        )


@dataclass(frozen=True, slots=True)
class FinanzOnlineCredentials:
    """Authentication credentials for FinanzOnline web services.

    Validation rules per login.xsd:
        - tid: 8-12 alphanumeric characters
        - benid: 5-12 characters
        - pin: 5-128 characters
        - herstellerid: 10-24 alphanumeric characters (VAT-ID of software producer)

    Attributes:
        tid: Participant ID (Teilnehmer-ID) - 8-12 alphanumeric chars.
        benid: User ID (Benutzer-ID) - 5-12 chars.
        pin: Password/PIN for authentication - 5-128 chars.
        herstellerid: VAT-ID of software producer - 10-24 alphanumeric chars.
    """

    tid: str
    benid: str
    pin: str
    herstellerid: str

    def __post_init__(self) -> None:
        """Validate credentials according to login.xsd schema."""
        _validate_required(self.tid, "tid", "Participant ID")
        _validate_pattern(self.tid, "tid", _TID_PATTERN, "8-12 alphanumeric characters")

        _validate_required(self.benid, "benid", "User ID")
        _validate_length_range(self.benid, "benid", _BENID_MIN_LEN, _BENID_MAX_LEN)

        _validate_required(self.pin, "pin", "Password")
        _validate_length_range(self.pin, "pin", _PIN_MIN_LEN, _PIN_MAX_LEN)

        _validate_required(self.herstellerid, "herstellerid", "Software Producer VAT-ID")
        _validate_pattern(self.herstellerid, "herstellerid", _HERSTELLERID_PATTERN, "10-24 alphanumeric characters")


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """Session information returned after successful login.

    Attributes:
        session_id: Session identifier for subsequent requests.
        return_code: Login return code (0 = success).
        message: Human-readable status message.
    """

    session_id: str
    return_code: int
    message: str

    @property
    def is_valid(self) -> bool:
        """Check if session was created successfully."""
        return self.return_code == _RC_UID_VALID and bool(self.session_id)


def _validate_uid_tn(uid_tn: str) -> None:
    """Validate own Austrian UID format."""
    _validate_required(uid_tn, "uid_tn", "own Austrian UID")
    if not uid_tn.upper().startswith("ATU"):
        raise ValueError("uid_tn must start with 'ATU'")


@dataclass(frozen=True, slots=True)
class UidCheckRequest:
    """Request parameters for Level 2 UID verification.

    Attributes:
        uid_tn: Own Austrian UID (must start with 'ATU').
        uid: Target EU VAT ID to verify (e.g., 'DE123456789').
        stufe: Query level - always 2 for Level 2 verification.
    """

    uid_tn: str
    uid: str
    stufe: int = 2

    def __post_init__(self) -> None:
        """Validate request parameters."""
        _validate_uid_tn(self.uid_tn)
        _validate_required(self.uid, "uid", "target VAT ID")
        if self.stufe != 2:
            raise ValueError("Only Level 2 queries are supported (stufe=2)")


@dataclass(frozen=True, slots=True)
class Address:
    """Company address from Level 2 UID verification.

    FinanzOnline returns addresses in 6 lines (adr_1 through adr_6).
    Empty lines are represented as empty strings.

    Attributes:
        line1: First address line (typically company name).
        line2: Second address line.
        line3: Third address line.
        line4: Fourth address line.
        line5: Fifth address line.
        line6: Sixth address line.
    """

    line1: str = ""
    line2: str = ""
    line3: str = ""
    line4: str = ""
    line5: str = ""
    line6: str = ""

    def as_lines(self) -> list[str]:
        """Return non-empty address lines as a list.

        Returns:
            List of non-empty address lines in order.

        Examples:
            >>> addr = Address(line1="Test GmbH", line3="1010 Wien")
            >>> addr.as_lines()
            ['Test GmbH', '1010 Wien']
        """
        return [line for line in (self.line1, self.line2, self.line3, self.line4, self.line5, self.line6) if line]

    def as_text(self, separator: str = "\n") -> str:
        """Return address as formatted text.

        Args:
            separator: Line separator (default: newline).

        Returns:
            Address lines joined by separator.

        Examples:
            >>> addr = Address(line1="Test GmbH", line2="Street 1")
            >>> addr.as_text()
            'Test GmbH\\nStreet 1'
        """
        return separator.join(self.as_lines())

    @property
    def is_empty(self) -> bool:
        """Check if address has no content."""
        return not any(self.as_lines())


def _utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class UidCheckResult:
    """Complete result from Level 2 UID verification.

    Attributes:
        uid: The VAT ID that was verified.
        return_code: FinanzOnline return code (0 = valid).
        message: Human-readable status message.
        name: Company name (if UID is valid).
        address: Company address (if UID is valid).
        timestamp: When the verification was performed (UTC).
        from_cache: Whether this result was retrieved from cache.
        cached_at: Original query timestamp if result is from cache.
    """

    uid: str
    return_code: int
    message: str
    name: str = ""
    address: Address | None = None
    timestamp: datetime = field(default_factory=_utc_now)
    from_cache: bool = False
    cached_at: datetime | None = None

    @property
    def is_valid(self) -> bool:
        """Check if the UID is valid (return_code == 0).

        Returns:
            True if UID verification succeeded with code 0.

        Examples:
            >>> result = UidCheckResult(uid="DE123", return_code=0, message="OK")
            >>> result.is_valid
            True
            >>> result = UidCheckResult(uid="DE123", return_code=1, message="Invalid")
            >>> result.is_valid
            False
        """
        return self.return_code == _RC_UID_VALID

    @property
    def is_invalid(self) -> bool:
        """Check if the UID is explicitly invalid (return_code == 1).

        Returns:
            True if UID was verified as invalid.
        """
        return self.return_code == _RC_UID_INVALID

    @property
    def has_company_info(self) -> bool:
        """Check if result contains company information.

        Returns:
            True if name or address is present.
        """
        return bool(self.name) or (self.address is not None and not self.address.is_empty)


@dataclass(frozen=True, slots=True)
class NotificationOptions:
    """Options for notification handling in CLI commands.

    Groups notification-related options that travel together to reduce
    parameter list length.

    Attributes:
        enabled: Whether notifications should be sent.
        recipients: Explicit recipients (empty list uses config defaults).
    """

    enabled: bool = True
    recipients: tuple[str, ...] = ()
