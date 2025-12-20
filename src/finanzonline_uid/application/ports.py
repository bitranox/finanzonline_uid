"""Port definitions for external dependencies.

Purpose
-------
Define protocol interfaces (ports) that abstract external dependencies.
Adapters implement these protocols to integrate with actual services.

Contents
--------
* :class:`SessionPort` - Session management interface
* :class:`UidQueryPort` - UID query interface
* :class:`NotificationPort` - Notification delivery interface

System Role
-----------
Application layer - defines contracts for Dependency Inversion Principle.
Use cases depend on these abstractions, not concrete implementations.

Examples
--------
>>> class MockSessionPort:
...     def login(self, credentials):
...         return SessionInfo(session_id="test", return_code=0, message="OK")
...     def logout(self, session_id, credentials):
...         return True
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from finanzonline_uid.domain.models import (
        FinanzOnlineCredentials,
        SessionInfo,
        UidCheckRequest,
        UidCheckResult,
    )


class SessionPort(Protocol):
    """Port for FinanzOnline session management.

    Defines the contract for login/logout operations with the
    FinanzOnline Session Webservice.

    Implementations must handle SOAP communication with the BMF
    session service endpoint.
    """

    def login(self, credentials: FinanzOnlineCredentials) -> SessionInfo:
        """Authenticate with FinanzOnline and obtain a session.

        Args:
            credentials: FinanzOnline credentials (tid, benid, pin).

        Returns:
            SessionInfo with session_id if successful.

        Raises:
            AuthenticationError: If credentials are invalid.
            SessionError: If session creation fails.
        """
        ...

    def logout(self, session_id: str, credentials: FinanzOnlineCredentials) -> bool:
        """End a FinanzOnline session.

        Args:
            session_id: Active session identifier.
            credentials: FinanzOnline credentials.

        Returns:
            True if logout succeeded, False otherwise.
            Logout failures are typically not critical.
        """
        ...


class UidQueryPort(Protocol):
    """Port for UID verification queries.

    Defines the contract for executing Level 2 UID queries against
    the FinanzOnline UID-Abfrage Webservice.

    Implementations must handle SOAP communication with the BMF
    UID query service endpoint.
    """

    def query(
        self,
        session_id: str,
        credentials: FinanzOnlineCredentials,
        request: UidCheckRequest,
    ) -> UidCheckResult:
        """Execute a Level 2 UID verification query.

        Args:
            session_id: Active session identifier from login.
            credentials: FinanzOnline credentials (tid, benid).
            request: UID check request with own UID and target UID.

        Returns:
            UidCheckResult with verification status and company info.

        Raises:
            SessionError: If session is invalid or expired.
            QueryError: If query execution fails.
        """
        ...


class NotificationPort(Protocol):
    """Port for sending result notifications.

    Defines the contract for delivering UID verification results
    to recipients via email or other channels.

    Implementations handle email formatting and delivery using
    the configured mail infrastructure.
    """

    def send_result(
        self,
        result: UidCheckResult,
        recipients: list[str],
    ) -> bool:
        """Send verification result notification.

        Args:
            result: UID verification result to notify about.
            recipients: Email addresses to send notification to.

        Returns:
            True if notification sent successfully, False otherwise.
            Notification failures are typically non-fatal.
        """
        ...
