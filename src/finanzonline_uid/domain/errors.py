"""Domain exceptions for UID verification.

Purpose
-------
Define a hierarchy of domain-specific exceptions that represent
business error conditions in the UID verification process.

Contents
--------
* :class:`ErrorKind` - Category of a failed check, as shown to the reader
* :class:`CheckErrorInfo` - Consolidated error details for reporting
* :class:`UidCheckError` - Base exception for all UID check errors
* :class:`ConfigurationError` - Missing or invalid configuration
* :class:`AuthenticationError` - Login/credentials failure
* :class:`SessionError` - Session management errors
* :class:`QueryError` - UID query execution errors
* :class:`ServiceMaintenanceError` - FinanzOnline service in maintenance

System Role
-----------
Domain layer - pure exception definitions with no I/O dependencies.
Application layer catches and handles these exceptions appropriately.

Examples
--------
>>> raise ConfigurationError("Missing tid credential")
Traceback (most recent call last):
    ...
finanzonline_uid.domain.errors.ConfigurationError: Missing tid credential

>>> from finanzonline_uid.domain.models import Diagnostics, SoapOperation
>>> diag = Diagnostics(operation=SoapOperation.UID_QUERY, return_code="1513")
>>> err = QueryError("Rate limit exceeded", return_code=1513, retryable=True, diagnostics=diag)
>>> err.retryable
True
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from finanzonline_uid.domain.models import Diagnostics

if TYPE_CHECKING:
    from finanzonline_uid.domain.return_codes import CliExitCode


class ErrorKind(str, Enum):
    """Category of a failed UID check.

    The value is the label shown in console output, JSON output (``error_type``)
    and error emails, so it is part of the output format.

    Examples:
        >>> ErrorKind.SESSION.value
        'Session Error'
    """

    CONFIGURATION = "Configuration Error"
    AUTHENTICATION = "Authentication Error"
    SERVICE_MAINTENANCE = "Service Maintenance"
    SESSION = "Session Error"
    QUERY = "Query Error"
    UID_CHECK = "UID Check Error"
    VALIDATION = "Validation Error"
    UNEXPECTED = "Unexpected Error"
    CANCELLED = "Cancelled"


@dataclass(frozen=True, slots=True)
class CheckErrorInfo:
    """Consolidated error information for check command error handling.

    Groups all error-related data that would otherwise be passed as
    separate parameters, reducing parameter list length and improving
    code clarity.

    Attributes:
        error_type: Category of the failure; its value is the display label.
        message: Human-readable error description.
        exit_code: CLI exit code to return.
        return_code: Optional FinanzOnline return code.
        retryable: Whether the error is temporary/retryable.
        diagnostics: Optional diagnostics for debugging.
    """

    error_type: ErrorKind
    message: str
    exit_code: CliExitCode
    return_code: int | None = None
    retryable: bool = False
    diagnostics: Diagnostics | None = None


class UidCheckError(Exception):
    """Base exception for all UID check errors.

    All domain-specific exceptions inherit from this class to enable
    catching all UID check errors with a single except clause.

    Every subclass carries the same reporting attributes, so a handler reads them
    directly instead of probing for them.

    Attributes:
        message: Human-readable error description.
        return_code: FinanzOnline return code, when the service sent one.
        retryable: Whether the operation may succeed if retried later.
        diagnostics: Request/response details with masked credentials.
    """

    def __init__(self, message: str) -> None:
        """Initialize with error message.

        Args:
            message: Human-readable error description.
        """
        self.message = message
        self.return_code: int | None = None
        self.retryable: bool = False
        self.diagnostics: Diagnostics = Diagnostics()
        super().__init__(message)


class ConfigurationError(UidCheckError):
    """Configuration is missing or invalid.

    Raised when required configuration values are missing or when
    configuration validation fails.

    Examples:
        - Missing FinanzOnline credentials (tid, benid, pin)
        - Invalid uid_tn format (must start with ATU)
        - Missing email configuration when notifications enabled
    """


class AuthenticationError(UidCheckError):
    """Authentication with FinanzOnline failed.

    Raised when login fails due to invalid credentials or when
    the account is not authorized for UID queries.

    Attributes:
        message: Human-readable error description.
        return_code: FinanzOnline return code (if available).
        diagnostics: Diagnostics object with request/response details.
    """

    def __init__(
        self,
        message: str,
        *,
        return_code: int | None = None,
        diagnostics: Diagnostics | None = None,
    ) -> None:
        """Initialize with error details.

        Args:
            message: Human-readable error description.
            return_code: Optional FinanzOnline return code.
            diagnostics: Optional Diagnostics object with masked credentials.
        """
        super().__init__(message)
        self.return_code = return_code
        self.diagnostics = diagnostics or Diagnostics()


class SessionError(UidCheckError):
    """Session management error.

    Raised when session operations fail, such as:
    - Session creation timeout
    - Session expired during query
    - Logout failure

    Attributes:
        message: Human-readable error description.
        return_code: FinanzOnline return code (if available).
        diagnostics: Diagnostics object with request/response details.
    """

    def __init__(
        self,
        message: str,
        *,
        return_code: int | None = None,
        diagnostics: Diagnostics | None = None,
    ) -> None:
        """Initialize with error details.

        Args:
            message: Human-readable error description.
            return_code: Optional FinanzOnline return code.
            diagnostics: Optional Diagnostics object with masked credentials.
        """
        super().__init__(message)
        self.return_code = return_code
        self.diagnostics = diagnostics or Diagnostics()


class QueryError(UidCheckError):
    """UID query execution failed.

    Raised when the UID query cannot be completed, such as:
    - Network/connectivity issues
    - Service unavailable (maintenance)
    - Rate limit exceeded
    - Invalid query parameters

    Attributes:
        message: Human-readable error description.
        return_code: FinanzOnline return code (if available).
        retryable: Whether the operation may succeed if retried later.
        diagnostics: Diagnostics object with request/response details.
    """

    def __init__(
        self,
        message: str,
        *,
        return_code: int | None = None,
        retryable: bool = False,
        diagnostics: Diagnostics | None = None,
    ) -> None:
        """Initialize with error details.

        Args:
            message: Human-readable error description.
            return_code: Optional FinanzOnline return code.
            retryable: Whether retry may succeed.
            diagnostics: Optional Diagnostics object with masked credentials.
        """
        super().__init__(message)
        self.return_code = return_code
        self.retryable = retryable
        self.diagnostics = diagnostics or Diagnostics()


class ServiceMaintenanceError(SessionError):
    """FinanzOnline service is in maintenance mode.

    Raised when the service returns HTML (e.g. a maintenance page) instead
    of a SOAP XML response. Always retryable since maintenance windows end.

    Attributes:
        message: Human-readable error description.
        retryable: Always True for maintenance errors.
        diagnostics: Diagnostics object with request/response details.
    """

    def __init__(
        self,
        message: str,
        *,
        diagnostics: Diagnostics | None = None,
    ) -> None:
        """Initialize with error details.

        Args:
            message: Human-readable error description.
            diagnostics: Optional Diagnostics object with masked credentials.
        """
        super().__init__(message, diagnostics=diagnostics)
        self.retryable = True
