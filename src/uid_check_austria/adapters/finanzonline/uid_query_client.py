"""FinanzOnline UID query adapter.

Purpose
-------
Implement UidQueryPort for Level 2 UID verification queries
against BMF FinanzOnline UID-Abfrage webservice using SOAP/zeep.

Contents
--------
* :class:`FinanzOnlineQueryClient` - UID query adapter

System Role
-----------
Adapters layer - SOAP client for FinanzOnline UID query webservice.

Reference
---------
BMF UID-Abfrage Webservice: https://finanzonline.bmf.gv.at/fonuid/ws/uidAbfrageService.wsdl
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

from zeep import Client
from zeep.exceptions import Fault, TransportError

from uid_check_austria.domain.errors import QueryError, SessionError
from uid_check_austria.domain.models import Address, Diagnostics, UidCheckResult

if TYPE_CHECKING:
    from uid_check_austria.domain.models import (
        FinanzOnlineCredentials,
        UidCheckRequest,
    )


logger = logging.getLogger(__name__)

UID_QUERY_SERVICE_WSDL = "https://finanzonline.bmf.gv.at/fonuid/ws/uidAbfrageService.wsdl"


def _mask_value(value: str, visible_chars: int = 4) -> str:
    """Mask a sensitive value, showing only first/last few characters.

    Args:
        value: The sensitive value to mask.
        visible_chars: Number of characters to show at start and end.

    Returns:
        Masked string like "abc...xyz" or "****" for short values.
    """
    if len(value) <= visible_chars * 2:
        return "*" * len(value)
    return f"{value[:visible_chars]}...{value[-visible_chars:]}"


def _format_query_request(
    session_id: str,
    credentials: FinanzOnlineCredentials,
    request: UidCheckRequest,
) -> dict[str, Any]:
    """Format query request parameters for debug logging (masked)."""
    return {
        "tid": credentials.tid,
        "benid": credentials.benid,
        "id": _mask_value(session_id) if session_id else "?",
        "uid_tn": request.uid_tn,
        "uid": request.uid,
        "stufe": request.stufe,
    }


def _extract_core_fields(response: Any, attrs: list[str]) -> dict[str, Any]:
    """Extract specified attributes from response if they exist."""
    return {attr: getattr(response, attr) for attr in attrs if hasattr(response, attr)}


def _extract_address_lines(response: Any) -> list[str]:
    """Extract non-empty address lines from response (adr_1 through adr_6)."""
    lines = []
    for i in range(1, 7):
        value = getattr(response, f"adr_{i}", None)
        if value:
            lines.append(str(value))
    return lines


def _format_query_response(response: Any) -> dict[str, Any]:
    """Format SOAP query response object for debug logging."""
    if response is None:
        return {"response": None}

    result = _extract_core_fields(response, ["rc", "msg", "name"])
    address_lines = _extract_address_lines(response)
    if address_lines:
        result["address"] = address_lines
    return result


def _build_query_diagnostics(
    session_id: str,
    credentials: FinanzOnlineCredentials,
    request: UidCheckRequest,
    response: Any | None = None,
    error: str | None = None,
) -> Diagnostics:
    """Build diagnostic information for UID query operation.

    Args:
        session_id: Active session ID (will be masked).
        credentials: The credentials used.
        request: The UID check request.
        response: Optional SOAP response object.
        error: Optional error message.

    Returns:
        Diagnostics object with diagnostic information.
    """
    return_code = ""
    response_message = ""

    if response is not None:
        return_code = str(getattr(response, "rc", ""))
        response_message = str(getattr(response, "msg", "") or "")

    return Diagnostics(
        operation="uidAbfrage",
        tid=credentials.tid,
        benid=credentials.benid,
        pin=_mask_value(credentials.pin),
        session_id=_mask_value(session_id),
        uid_tn=request.uid_tn,
        target_uid=request.uid,
        return_code=return_code,
        response_message=response_message,
        error_detail=error or "",
    )


def _extract_address_line(response: Any, attr_name: str) -> str:
    """Extract a single address line from response, defaulting to empty string."""
    return str(cast(str, getattr(response, attr_name, "")) or "")


def _extract_company_info(response: Any) -> tuple[str, Address | None]:
    """Extract company name and address from successful query response.

    Args:
        response: SOAP response with company data.

    Returns:
        Tuple of (company_name, address) from response.
    """
    name = str(cast(str, response.name) or "") if hasattr(response, "name") else ""
    address = Address(
        line1=_extract_address_line(response, "adr_1"),
        line2=_extract_address_line(response, "adr_2"),
        line3=_extract_address_line(response, "adr_3"),
        line4=_extract_address_line(response, "adr_4"),
        line5=_extract_address_line(response, "adr_5"),
        line6=_extract_address_line(response, "adr_6"),
    )
    return name, address


def _handle_query_exception(
    exc: Exception,
    session_id: str,
    credentials: FinanzOnlineCredentials,
    request: UidCheckRequest,
    response: Any | None,
) -> None:
    """Handle exceptions during UID query and raise appropriate domain error.

    Args:
        exc: The exception that occurred.
        session_id: Active session ID.
        credentials: FinanzOnline credentials.
        request: The UID check request.
        response: Optional SOAP response.

    Raises:
        SessionError: For session-related errors.
        QueryError: For all other query errors.
    """
    if isinstance(exc, (SessionError, QueryError)):
        raise

    diagnostics = _build_query_diagnostics(session_id, credentials, request, response, error=str(exc))

    if isinstance(exc, Fault):
        logger.error("SOAP fault during UID query: %s", exc)
        raise QueryError(f"SOAP fault: {exc.message}", diagnostics=diagnostics) from exc

    if isinstance(exc, TransportError):
        logger.error("Transport error during UID query: %s", exc)
        raise QueryError(f"Connection error: {exc}", retryable=True, diagnostics=diagnostics) from exc

    logger.error("Unexpected error during UID query: %s", exc)
    raise QueryError(f"Unexpected error: {exc}", diagnostics=diagnostics) from exc


class FinanzOnlineQueryClient:
    """SOAP client for FinanzOnline UID queries.

    Implements UidQueryPort protocol for Level 2 UID verification
    against the BMF UID-Abfrage webservice.

    Attributes:
        _timeout: Request timeout in seconds.
        _client: Zeep SOAP client (lazy-initialized).
    """

    def __init__(self, timeout: float = 30.0) -> None:
        """Initialize query client.

        Args:
            timeout: Request timeout in seconds.
        """
        self._timeout = timeout
        self._client: Client | None = None

    def _get_client(self) -> Client:
        """Get or create SOAP client.

        Returns:
            Zeep Client instance for UID query service.
        """
        if self._client is None:
            logger.debug("Creating UID query service client")
            self._client = Client(UID_QUERY_SERVICE_WSDL)
        return self._client

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
            SessionError: If session is invalid or expired (code -1).
            QueryError: If query execution fails.
        """
        logger.debug("Querying UID %s with uid_tn=%s, stufe=%d", request.uid, request.uid_tn, request.stufe)
        response: Any = None

        try:
            response = self._execute_soap_query(session_id, credentials, request)
            return self._process_query_response(session_id, credentials, request, response)
        except Exception as e:
            _handle_query_exception(e, session_id, credentials, request, response)
            raise  # Unreachable but satisfies type checker

    def _execute_soap_query(
        self,
        session_id: str,
        credentials: FinanzOnlineCredentials,
        request: UidCheckRequest,
    ) -> Any:
        """Execute the SOAP query call."""
        client = self._get_client()
        logger.debug("UID query request: %s", _format_query_request(session_id, credentials, request))
        response = client.service.uidAbfrage(
            tid=credentials.tid,
            benid=credentials.benid,
            id=session_id,
            uid_tn=request.uid_tn,
            uid=request.uid,
            stufe=request.stufe,
        )
        logger.debug("UID query response: %s", _format_query_response(response))
        return response

    def _process_query_response(
        self,
        session_id: str,
        credentials: FinanzOnlineCredentials,
        request: UidCheckRequest,
        response: Any,
    ) -> UidCheckResult:
        """Process SOAP response and build result."""
        return_code = int(cast(int, response.rc))
        message = str(cast(str, response.msg) or "")

        logger.debug("Query response: rc=%d, msg=%s", return_code, message)

        if return_code == -1:
            diagnostics = _build_query_diagnostics(session_id, credentials, request, response)
            raise SessionError(f"Session invalid or expired: {message}", return_code=return_code, diagnostics=diagnostics)

        name, address = ("", None)
        if return_code == 0:
            name, address = _extract_company_info(response)
            logger.info("UID %s is valid: %s", request.uid, name)
        else:
            logger.info("UID %s verification returned code %d: %s", request.uid, return_code, message)

        return UidCheckResult(
            uid=request.uid,
            return_code=return_code,
            message=message,
            name=name,
            address=address,
            timestamp=datetime.now(timezone.utc),
        )
