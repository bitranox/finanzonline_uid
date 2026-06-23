"""Application layer for finanzonline_uid.

Purpose
-------
Contains application use cases and port definitions (interfaces) that
define the boundary between the application and external systems.

Contents
--------
* :mod:`.ports` - Protocol definitions for external dependencies
* :mod:`.use_cases` - Application use cases (CheckUidUseCase)

System Role
-----------
Orchestration layer in clean architecture. Depends on domain layer,
defines contracts (ports) that adapters implement. Contains no I/O
implementation details.
"""

from __future__ import annotations

from .ports import (
    NotificationPort,
    SessionPort,
    UidQueryPort,
)
from .use_cases import (
    CheckUidUseCase,
)

__all__ = [
    # Ports
    "NotificationPort",
    "SessionPort",
    "UidQueryPort",
    # Use cases
    "CheckUidUseCase",
]
