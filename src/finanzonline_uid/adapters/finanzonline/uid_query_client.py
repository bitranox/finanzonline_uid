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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

from zeep import Client
from zeep.exceptions import Fault, TransportError
from zeep.transports import Transport

from finanzonline_uid.domain.errors import QueryError, ServiceMaintenanceError, SessionError
from finanzonline_uid.domain.models import Address, Diagnostics, UidCheckResult
from finanzonline_uid.domain.return_codes import ReturnCode
from finanzonline_uid.domain.soap_utils import extract_string_attr, extract_text_from_html_error, is_html_response_error

if TYPE_CHECKING:
    from finanzonline_uid.domain.models import (
        FinanzOnlineCredentials,
        UidCheckRequest,
    )


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SoapUidQueryResponse:
    """Typed representation of SOAP UID query response from FinanzOnline.

    Attributes:
        return_code: Integer return code from BMF (0 = valid, 1 = invalid, etc.).
        message: Response message from BMF.
        name: Company name (only present for valid UIDs).
        address: Company address (only present for valid UIDs).
    """

    return_code: int
    message: str
    name: str
    address: Address

    @classmethod
    def from_zeep(cls, response: Any) -> SoapUidQueryResponse:
        """Extract typed response from zeep SOAP response object.

        Args:
            response: Raw zeep response object with rc, msg, name, adrz1-6 attributes.

        Returns:
            Typed SoapUidQueryResponse with extracted values.

        Note:
            BMF returns address fields as adrz1-adrz6 (not adr_1-adr_6).
        """
        return cls(
            return_code=int(cast(int, response.rc)) if hasattr(response, "rc") else 0,
            message=extract_string_attr(response, "msg"),
            name=extract_string_attr(response, "name"),
            address=Address(
                line1=extract_string_attr(response, "adrz1"),
                line2=extract_string_attr(response, "adrz2"),
                line3=extract_string_attr(response, "adrz3"),
                line4=extract_string_attr(response, "adrz4"),
                line5=extract_string_attr(response, "adrz5"),
                line6=extract_string_attr(response, "adrz6"),
            ),
        )


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
        "tid": _mask_value(credentials.tid),
        "benid": _mask_value(credentials.benid),
        "id": _mask_value(session_id) if session_id else "?",
        "uid_tn": request.uid_tn,
        "uid": request.uid,
        "stufe": request.stufe,
    }


def _extract_core_fields(response: Any, attrs: list[str]) -> dict[str, Any]:
    """Extract specified attributes from response if they exist."""
    return {attr: getattr(response, attr) for attr in attrs if hasattr(response, attr)}


def _extract_address_lines(response: Any) -> list[str]:
    """Extract non-empty address lines from response (adrz1 through adrz6)."""
    lines = []
    for i in range(1, 7):
        value = getattr(response, f"adrz{i}", None)
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
        typed_response = SoapUidQueryResponse.from_zeep(response)
        return_code = str(typed_response.return_code)
        response_message = typed_response.message

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

    if is_html_response_error(exc):
        message = extract_text_from_html_error(exc)
        logger.warning("FinanzOnline returned HTML instead of SOAP XML (likely maintenance): %s", exc)
        raise ServiceMaintenanceError(message, diagnostics=diagnostics) from exc

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
            logger.debug("Creating UID query service client with timeout=%s", self._timeout)
            transport = Transport(timeout=self._timeout, operation_timeout=self._timeout)
            self._client = Client(UID_QUERY_SERVICE_WSDL, transport=transport)
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
        typed_response = SoapUidQueryResponse.from_zeep(response)

        logger.debug("Query response: rc=%d, msg=%s", typed_response.return_code, typed_response.message)

        if typed_response.return_code == ReturnCode.SESSION_INVALID:
            diagnostics = _build_query_diagnostics(session_id, credentials, request, response)
            raise SessionError(f"Session invalid or expired: {typed_response.message}", return_code=typed_response.return_code, diagnostics=diagnostics)

        name: str = ""
        address: Address | None = None
        if typed_response.return_code == ReturnCode.UID_VALID:
            name = typed_response.name
            address = typed_response.address
            logger.info("UID %s is valid: %s", request.uid, name)
        else:
            logger.info("UID %s verification returned code %d: %s", request.uid, typed_response.return_code, typed_response.message)

        return UidCheckResult(
            uid=request.uid,
            return_code=typed_response.return_code,
            message=typed_response.message,
            name=name,
            address=address,
            timestamp=datetime.now(timezone.utc),
        )
