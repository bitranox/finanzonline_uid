"""Domain exceptions for UID verification.

Purpose
-------
Define a hierarchy of domain-specific exceptions that represent
business error conditions in the UID verification process.

Contents
--------
* :class:`UidCheckError` - Base exception for all UID check errors
* :class:`ConfigurationError` - Missing or invalid configuration
* :class:`AuthenticationError` - Login/credentials failure
* :class:`SessionError` - Session management errors
* :class:`QueryError` - UID query execution errors

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

>>> from finanzonline_uid.domain.models import Diagnostics
>>> diag = Diagnostics(operation="query", return_code="1513")
>>> err = QueryError("Rate limit exceeded", return_code=1513, retryable=True, diagnostics=diag)
>>> err.retryable
True
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from finanzonline_uid.domain.models import Diagnostics

if TYPE_CHECKING:
    from finanzonline_uid.domain.return_codes import CliExitCode


@dataclass(frozen=True, slots=True)
class CheckErrorInfo:
    """Consolidated error information for check command error handling.

    Groups all error-related data that would otherwise be passed as
    separate parameters, reducing parameter list length and improving
    code clarity.

    Attributes:
        error_type: Type label for display (e.g., "Authentication Error").
        message: Human-readable error description.
        exit_code: CLI exit code to return.
        return_code: Optional FinanzOnline return code.
        retryable: Whether the error is temporary/retryable.
        diagnostics: Optional diagnostics for debugging.
    """

    error_type: str
    message: str
    exit_code: "CliExitCode"
    return_code: int | None = None
    retryable: bool = False
    diagnostics: Diagnostics | None = None


class UidCheckError(Exception):
    """Base exception for all UID check errors.

    All domain-specific exceptions inherit from this class to enable
    catching all UID check errors with a single except clause.

    Attributes:
        message: Human-readable error description.
    """

    def __init__(self, message: str) -> None:
        """Initialize with error message.

        Args:
            message: Human-readable error description.
        """
        self.message = message
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
