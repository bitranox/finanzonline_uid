"""FinanzOnline SOAP client adapters.

Purpose
-------
Implement SessionPort and UidQueryPort using zeep SOAP client
to communicate with BMF FinanzOnline web services.

Contents
--------
* :class:`.session_client.FinanzOnlineSessionClient` - Session management
* :class:`.uid_query_client.FinanzOnlineQueryClient` - UID queries

System Role
-----------
Adapters layer - implements application ports with actual SOAP calls.
"""

from __future__ import annotations

from .session_client import FinanzOnlineSessionClient
from .uid_query_client import FinanzOnlineQueryClient

__all__ = [
    "FinanzOnlineQueryClient",
    "FinanzOnlineSessionClient",
]
