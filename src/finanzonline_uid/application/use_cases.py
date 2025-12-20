"""Application use cases for UID verification.

Purpose
-------
Orchestrate UID verification operations by coordinating between
domain models and adapter ports. Contains the core business logic
flow without implementation details.

Contents
--------
* :class:`CheckUidUseCase` - Main use case for UID verification

System Role
-----------
Application layer - orchestrates domain operations through ports.
Depends on domain models and port protocols, not concrete adapters.

Examples
--------
>>> use_case = CheckUidUseCase(session_client, query_client)  # doctest: +SKIP
>>> result = use_case.execute(credentials, "ATU12345678", "DE987654321")  # doctest: +SKIP
>>> result.is_valid  # doctest: +SKIP
True
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from finanzonline_uid.domain.errors import SessionError
from finanzonline_uid.domain.models import UidCheckRequest

if TYPE_CHECKING:
    from finanzonline_uid.adapters.cache import UidResultCache
    from finanzonline_uid.adapters.ratelimit import RateLimitStatus, RateLimitTracker
    from finanzonline_uid.application.ports import SessionPort, UidQueryPort
    from finanzonline_uid.domain.models import (
        FinanzOnlineCredentials,
        SessionInfo,
        UidCheckResult,
    )


logger = logging.getLogger(__name__)


class CheckUidUseCase:
    """Use case for executing Level 2 UID verification.

    Orchestrates the complete UID verification flow:
    1. Check cache for existing valid result
    2. Check rate limit and warn if exceeded
    3. Login to FinanzOnline session service
    4. Execute Level 2 UID query
    5. Cache valid results
    6. Logout from session (always, even on error)

    Attributes:
        _session_client: Session management port implementation.
        _query_client: UID query port implementation.
        _cache: Optional cache for storing/retrieving results.
        _rate_limiter: Optional rate limit tracker.
        _rate_limit_notifier: Optional callback for rate limit warnings.
    """

    def __init__(
        self,
        session_client: SessionPort,
        query_client: UidQueryPort,
        cache: UidResultCache | None = None,
        rate_limiter: RateLimitTracker | None = None,
        rate_limit_notifier: Callable[[RateLimitStatus], None] | None = None,
    ) -> None:
        """Initialize use case with required adapters.

        Args:
            session_client: Implementation of SessionPort for login/logout.
            query_client: Implementation of UidQueryPort for UID queries.
            cache: Optional cache adapter for caching results.
            rate_limiter: Optional rate limit tracker for API call tracking.
            rate_limit_notifier: Optional callback invoked when rate limit exceeded.
        """
        self._session_client = session_client
        self._query_client = query_client
        self._cache = cache
        self._rate_limiter = rate_limiter
        self._rate_limit_notifier = rate_limit_notifier

    def _try_get_cached(self, target_uid: str) -> UidCheckResult | None:
        """Check cache and return cached result if available."""
        if self._cache is None:
            return None
        cached_result = self._cache.get(target_uid)
        if cached_result is not None:
            logger.info("Returning cached result for %s", target_uid)
        return cached_result

    def _handle_rate_limit(self, target_uid: str) -> None:
        """Record API call and notify if rate limit exceeded."""
        if self._rate_limiter is None:
            return
        status = self._rate_limiter.record_call(target_uid)
        if not status.is_exceeded:
            return
        logger.warning(
            "Rate limit exceeded: %d/%d queries in %.1f hours",
            status.current_count,
            status.max_queries,
            status.window_hours,
        )
        if self._rate_limit_notifier is not None:
            self._rate_limit_notifier(status)

    def _cache_valid_result(self, result: UidCheckResult) -> None:
        """Cache result if caching is enabled and result is valid."""
        if self._cache is not None and result.is_valid:
            self._cache.put(result)

    def _logout_safely(self, session_id: str, credentials: FinanzOnlineCredentials) -> None:
        """Logout from session, logging but not raising on failure."""
        try:
            self._session_client.logout(session_id, credentials)
        except Exception as e:
            logger.warning("Logout failed (non-fatal): %s", e)

    def execute(
        self,
        credentials: FinanzOnlineCredentials,
        uid_tn: str,
        target_uid: str,
    ) -> UidCheckResult:
        """Execute Level 2 UID verification.

        Args:
            credentials: FinanzOnline credentials.
            uid_tn: Own Austrian UID (must start with 'ATU').
            target_uid: Target EU VAT ID to verify.

        Returns:
            UidCheckResult with verification status and company info.
            If result is from cache, from_cache=True and cached_at is set.

        Raises:
            SessionError: Login or session management failed.
            QueryError: UID query execution failed.
            ValueError: Invalid request parameters.
        """
        logger.info("Starting UID check for %s", target_uid)

        cached_result = self._try_get_cached(target_uid)
        if cached_result is not None:
            return cached_result

        self._handle_rate_limit(target_uid)
        request = UidCheckRequest(uid_tn=uid_tn, uid=target_uid, stufe=2)
        session = self._login_or_raise(credentials)

        try:
            result = self._execute_query(session.session_id, credentials, request, target_uid)
            self._cache_valid_result(result)
            return result
        finally:
            logger.debug("Logging out from FinanzOnline")
            self._logout_safely(session.session_id, credentials)

    def _login_or_raise(self, credentials: FinanzOnlineCredentials) -> SessionInfo:
        """Login to FinanzOnline, raising SessionError on failure."""
        logger.debug("Logging in to FinanzOnline")
        session = self._session_client.login(credentials)
        if not session.is_valid:
            raise SessionError(f"Login failed: {session.message}", return_code=session.return_code)
        logger.debug("Session established: %s...", session.session_id[:8])
        return session

    def _execute_query(
        self,
        session_id: str,
        credentials: FinanzOnlineCredentials,
        request: UidCheckRequest,
        target_uid: str,
    ) -> UidCheckResult:
        """Execute UID query and log result."""
        logger.debug("Executing UID query for %s", target_uid)
        result = self._query_client.query(session_id=session_id, credentials=credentials, request=request)
        logger.info(
            "UID check completed: %s = %s (code %d)",
            target_uid,
            "VALID" if result.is_valid else "INVALID",
            result.return_code,
        )
        return result
