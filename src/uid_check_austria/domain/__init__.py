"""Domain layer for uid_check_austria.

Purpose
-------
Contains pure domain models, value objects, and business rules with no external
dependencies. This layer represents the core business logic for UID verification.

Contents
--------
* :mod:`.models` - Immutable dataclasses for domain entities
* :mod:`.errors` - Domain-specific exception hierarchy
* :mod:`.return_codes` - FinanzOnline return code definitions

System Role
-----------
Innermost layer in clean architecture - has no dependencies on application,
adapters, or infrastructure layers. All other layers depend on domain.
"""

from __future__ import annotations

from .errors import (
    AuthenticationError,
    ConfigurationError,
    QueryError,
    SessionError,
    UidCheckError,
)
from .models import (
    Address,
    FinanzOnlineCredentials,
    SessionInfo,
    UidCheckRequest,
    UidCheckResult,
)
from .return_codes import (
    ReturnCode,
    ReturnCodeInfo,
    Severity,
    get_return_code_info,
)

__all__ = [
    # Models
    "Address",
    "FinanzOnlineCredentials",
    "SessionInfo",
    "UidCheckRequest",
    "UidCheckResult",
    # Errors
    "AuthenticationError",
    "ConfigurationError",
    "QueryError",
    "SessionError",
    "UidCheckError",
    # Return codes
    "ReturnCode",
    "ReturnCodeInfo",
    "Severity",
    "get_return_code_info",
]
