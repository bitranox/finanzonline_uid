"""FinanzOnline UID query adapter.

Purpose
-------
Implement UidQueryPort for Level 2 UID verification queries
against BMF FinanzOnline UID-Abfrage webservice using SOAP/zeep.

Contents
--------
* :class:`FinanzOnlineQueryClient` - UID query adapter
* :class:`SoapUidQueryResponse` - Validated uidAbfrage reply

System Role
-----------
Adapters layer - SOAP client for FinanzOnline UID query webservice.

Reference
---------
BMF UID-Abfrage Webservice: https://finanzonline.bmf.gv.at/fonuid/ws/uidAbfrageService.wsdl
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal, Protocol, cast

from pydantic import BaseModel, Field, ValidationError
from zeep import Client
from zeep.exceptions import Fault, TransportError
from zeep.plugins import HistoryPlugin
from zeep.transports import Transport

from finanzonline_uid.adapters.finanzonline._soap_common import (
    MalformedSoapResponseError,
    SoapText,
    TransportFactory,
    describe_validation_error,
    mask_credential,
)
from finanzonline_uid.domain.errors import QueryError, ServiceMaintenanceError, SessionError
from finanzonline_uid.domain.models import Address, Diagnostics, SoapOperation, UidCheckResult
from finanzonline_uid.domain.return_codes import ReturnCode
from finanzonline_uid.domain.soap_utils import extract_text_from_html_error, is_html_response_error, is_zeep_parsing_error

if TYPE_CHECKING:
    from finanzonline_uid.domain.models import (
        FinanzOnlineCredentials,
        UidCheckRequest,
    )


__all__ = [
    "UID_QUERY_SERVICE_WSDL",
    "FinanzOnlineQueryClient",
    "SoapUidQueryResponse",
]


logger = logging.getLogger(__name__)


UID_QUERY_SERVICE_WSDL = "https://finanzonline.bmf.gv.at/fonuid/ws/uidAbfrageService.wsdl"

# Cap captured raw responses to avoid bloating logs/emails when BMF returns
# large blobs. 8 KB is plenty for a UID SOAP response (typically ~1 KB).
_RAW_RESPONSE_MAX_CHARS = 8192


class _UidQueryService(Protocol):
    """The uidAbfrage operation zeep builds from the WSDL at run time."""

    def uidAbfrage(self, *, tid: str, benid: str, id: str, uid_tn: str, uid: str, stufe: int) -> object:
        """Send uidAbfrageRequest; the reply is validated by :class:`SoapUidQueryResponse`."""
        ...


class _UidQuerySoapClient(Protocol):
    """The part of a zeep ``Client`` this adapter uses."""

    @property
    def service(self) -> _UidQueryService:
        """Service proxy bound to the WSDL's default port."""
        ...


class _HistoryEntry(BaseModel, frozen=True):
    """One side of an exchange as zeep's HistoryPlugin records it.

    zeep records ``{"envelope": ..., "http_headers": ...}``; only the envelope
    is read. The entry is parsed rather than indexed because this runs while an
    error is being reported: a missing key or an entry of another shape must
    read as "no envelope", not raise and replace the error being reported.

    Examples:
        >>> _HistoryEntry.model_validate({"http_headers": {}}).envelope is None
        True
    """

    # lxml element; typed object because lxml ships no type information.
    envelope: object | None = None


class _EnvelopeHistory(Protocol):
    """zeep's HistoryPlugin as read for diagnostics.

    Both properties raise IndexError while nothing has been sent yet. Their
    value is read as ``object`` and parsed by :class:`_HistoryEntry`.
    """

    @property
    def last_sent(self) -> object:
        """The request side of the last exchange."""
        ...

    @property
    def last_received(self) -> object:
        """The response side of the last exchange (None until a reply arrived)."""
        ...


class _XmlSerializer(Protocol):
    """``lxml.etree.tostring`` as this module calls it."""

    # Only encoding="unicode" makes tostring return str (any other value gives
    # bytes), so the facade admits that one value and no other.
    def __call__(self, element: object, *, pretty_print: bool, encoding: Literal["unicode"]) -> str:
        """Serialize an element to a str."""
        ...


def _xml_serializer() -> _XmlSerializer:
    """Return lxml's ``tostring`` behind a typed facade.

    lxml ships no type information, and zeep cannot run without it, so it is
    looked up here instead of imported by name. The lookup happens per call so
    a test patching ``lxml.etree.tostring`` is seen.
    """
    etree = importlib.import_module("lxml.etree")
    return cast("_XmlSerializer", etree.tostring)


class SoapUidQueryResponse(BaseModel, frozen=True, from_attributes=True):
    """Validated uidAbfrage reply from FinanzOnline.

    BMF documents the address as adr_1..adr_6, but the reply carries
    adrz1..adrz6; the aliases follow the reply.

    Attributes:
        return_code: Integer return code from BMF (0 = valid, 1 = invalid, etc.).
        message: Response message from BMF ("" when omitted).
        name: Company name (only present for valid UIDs).
        line1: Address line 1 (adrz1).
        line2: Address line 2 (adrz2).
        line3: Address line 3 (adrz3).
        line4: Address line 4 (adrz4).
        line5: Address line 5 (adrz5).
        line6: Address line 6 (adrz6).

    Examples:
        >>> from types import SimpleNamespace
        >>> reply = SoapUidQueryResponse.model_validate(SimpleNamespace(rc=0, msg=None, name="ACME", adrz1="Street 1", adrz6=None))
        >>> (reply.return_code, reply.message, reply.name, reply.address.as_lines())
        (0, '', 'ACME', ['Street 1'])
    """

    # Required: a missing code read as 0 would report the UID as VALID from a
    # reply that carries no verdict - a false positive on a VAT check.
    return_code: int = Field(validation_alias="rc")
    message: SoapText = Field(default="", validation_alias="msg")
    name: SoapText = ""
    line1: SoapText = Field(default="", validation_alias="adrz1")
    line2: SoapText = Field(default="", validation_alias="adrz2")
    line3: SoapText = Field(default="", validation_alias="adrz3")
    line4: SoapText = Field(default="", validation_alias="adrz4")
    line5: SoapText = Field(default="", validation_alias="adrz5")
    line6: SoapText = Field(default="", validation_alias="adrz6")

    @property
    def address(self) -> Address:
        """The six address lines as the domain's Address."""
        return Address(line1=self.line1, line2=self.line2, line3=self.line3, line4=self.line4, line5=self.line5, line6=self.line6)


def _parse_query_response(reply: object) -> SoapUidQueryResponse:
    """Parse a zeep uidAbfrage reply once into its validated record.

    Args:
        reply: The object zeep returned for uidAbfrageRequest.

    Returns:
        The validated record.

    Raises:
        MalformedSoapResponseError: When a field does not fit (a non-integer rc).
    """
    try:
        return SoapUidQueryResponse.model_validate(reply)
    except ValidationError as exc:
        problems = describe_validation_error(exc)
    # Raised outside the except block so the ValidationError, which holds the
    # reply, does not ride along as __context__.
    raise MalformedSoapResponseError(f"Malformed uidAbfrage response: {problems}")


def _read_envelope(read_entry: Callable[[], object]) -> object | None:
    """Return the envelope of one recorded side of the last exchange, if any.

    Args:
        read_entry: Reads ``last_sent`` or ``last_received`` from the history.

    Returns:
        The lxml envelope element, or None when nothing was recorded or the
        entry has no envelope or is not a mapping.

    Examples:
        >>> _read_envelope(lambda: {"http_headers": {}}) is None
        True
        >>> _read_envelope(lambda: "not an entry") is None
        True
    """
    try:
        raw_entry = read_entry()
    except (IndexError, AttributeError):
        return None
    try:
        entry = _HistoryEntry.model_validate(raw_entry)
    except ValidationError:
        return None
    return entry.envelope


def _serialize_envelope(envelope: object | None) -> str:
    """Serialize a captured envelope to XML.

    Args:
        envelope: The lxml envelope element, or None.

    Returns:
        Pretty-printed XML string (truncated to ~8 KB), or empty string
        if the envelope is not available or cannot be serialized.
    """
    if envelope is None:
        return ""

    try:
        raw = _xml_serializer()(envelope, pretty_print=True, encoding="unicode")
    except Exception as exc:  # noqa: BLE001 - diagnostics-only best effort, must not fail the caller
        logger.debug("Failed to serialize SOAP envelope: %s", exc)
        return ""

    if len(raw) > _RAW_RESPONSE_MAX_CHARS:
        raw = raw[:_RAW_RESPONSE_MAX_CHARS] + "\n... [truncated]"
    return raw


def _capture_raw_response(history: _EnvelopeHistory) -> str:
    """Capture raw XML from zeep's HistoryPlugin for failure diagnostics.

    Tries the received envelope first (the BMF response we couldn't parse),
    then falls back to indicating whether the request was sent. Always
    returns a non-empty string so failure emails carry useful context.

    Args:
        history: zeep HistoryPlugin instance attached to the client.

    Returns:
        Pretty-printed XML response, a fallback marker, or a placeholder
        explaining why nothing was captured.
    """
    received = _serialize_envelope(_read_envelope(lambda: history.last_received))
    if received:
        logger.info("Captured raw SOAP response (%d chars) for diagnostics", len(received))
        return received

    sent = _serialize_envelope(_read_envelope(lambda: history.last_sent))
    if sent:
        # Don't dump the request envelope - it contains tid/benid/pin/session_id
        # in cleartext. Just signal that the request went out but no response
        # came back / was parseable.
        logger.warning("No SOAP response captured; request was sent (size=%d)", len(sent))
        return "[Request was sent but no SOAP response was captured/parseable]"

    logger.warning("No SOAP envelope captured (HistoryPlugin buffer empty)")
    return "[No SOAP envelope captured - error occurred before HTTP exchange]"


def _build_query_diagnostics(
    session_id: str,
    credentials: FinanzOnlineCredentials,
    request: UidCheckRequest,
    parsed: SoapUidQueryResponse | None = None,
    error: str = "",
    raw_response: str = "",
) -> Diagnostics:
    """Build diagnostic information for UID query operation.

    Args:
        session_id: Active session ID (will be masked).
        credentials: The credentials used.
        request: The UID check request.
        parsed: The validated reply, if one was received and parsed.
        error: Optional error message.
        raw_response: Optional raw XML response captured for failure investigation.

    Returns:
        Diagnostics object with diagnostic information.
    """
    return Diagnostics(
        operation=SoapOperation.UID_QUERY,
        tid=credentials.tid,
        benid=credentials.benid,
        pin=mask_credential(credentials.pin),
        session_id=mask_credential(session_id),
        uid_tn=request.uid_tn,
        target_uid=request.uid,
        return_code="" if parsed is None else str(parsed.return_code),
        response_message="" if parsed is None else parsed.message,
        error_detail=error,
        raw_response=raw_response,
    )


def _query_error(
    exc: Exception,
    session_id: str,
    credentials: FinanzOnlineCredentials,
    request: UidCheckRequest,
    parsed: SoapUidQueryResponse | None,
    history: _EnvelopeHistory | None = None,
) -> QueryError | ServiceMaintenanceError:
    """Translate a failure during a UID query into the domain error to raise.

    Args:
        exc: The exception that occurred (never a domain error: those propagate as they are).
        session_id: Active session ID.
        credentials: FinanzOnline credentials.
        request: The UID check request.
        parsed: The validated reply, if parsing got that far.
        history: Optional zeep HistoryPlugin to capture the raw response from.

    Returns:
        ServiceMaintenanceError when BMF answered with an HTML maintenance page,
        otherwise a QueryError naming the failure (retryable for transport and
        zeep parsing failures).
    """
    raw_response = _capture_raw_response(history) if history is not None else ""
    diagnostics = _build_query_diagnostics(session_id, credentials, request, parsed, error=str(exc), raw_response=raw_response)

    if isinstance(exc, Fault):
        logger.error("SOAP fault during UID query: %s", exc)
        # str(Fault) is Fault.message (zeep passes it to Exception.__init__); reading
        # .message directly would go through zeep's untyped attribute.
        return QueryError(f"SOAP fault: {exc}", diagnostics=diagnostics)

    if isinstance(exc, TransportError):
        logger.error("Transport error during UID query: %s", exc)
        return QueryError(f"Connection error: {exc}", retryable=True, diagnostics=diagnostics)

    if is_html_response_error(exc):
        message = extract_text_from_html_error(exc)
        logger.warning("FinanzOnline returned HTML instead of SOAP XML (likely maintenance): %s", exc)
        return ServiceMaintenanceError(message, diagnostics=diagnostics)

    if is_zeep_parsing_error(exc):
        logger.warning("FinanzOnline returned a SOAP response zeep could not parse (likely transient cross-border VIES issue): %s", exc)
        return QueryError(
            f"Malformed response from FinanzOnline (transient, likely cross-border VIES issue): {exc}",
            retryable=True,
            diagnostics=diagnostics,
        )

    logger.error("Unexpected error during UID query: %s", exc)
    return QueryError(f"Unexpected error: {exc}", diagnostics=diagnostics)


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
        self._client: _UidQuerySoapClient | None = None
        # HistoryPlugin captures the last sent/received SOAP envelopes so we
        # can include the raw response in diagnostics when parsing fails. zeep
        # leaves the plugin's properties loosely typed; the cast states the two
        # this adapter reads, and _HistoryEntry parses what they return.
        self._history: _EnvelopeHistory = cast("_EnvelopeHistory", HistoryPlugin())

    def _get_client(self) -> _UidQuerySoapClient:
        """Get or create SOAP client.

        Returns:
            Zeep Client instance for UID query service.
        """
        if self._client is None:
            logger.debug("Creating UID query service client with timeout=%s", self._timeout)
            transport = cast("TransportFactory", Transport)(timeout=self._timeout, operation_timeout=self._timeout)
            # zeep builds `service` from the WSDL at run time, so nothing about it is
            # typed; this cast is the one place the adapter states what it relies on.
            self._client = cast("_UidQuerySoapClient", Client(UID_QUERY_SERVICE_WSDL, transport=transport, plugins=[self._history]))
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
        parsed: SoapUidQueryResponse | None = None

        try:
            parsed = self._execute_soap_query(session_id, credentials, request)
            return self._process_query_response(session_id, credentials, request, parsed)
        except (SessionError, QueryError):
            # Raised by this client with its own diagnostics already.
            raise
        except Exception as exc:
            raise _query_error(exc, session_id, credentials, request, parsed, history=self._history) from exc

    def _execute_soap_query(
        self,
        session_id: str,
        credentials: FinanzOnlineCredentials,
        request: UidCheckRequest,
    ) -> SoapUidQueryResponse:
        """Execute the SOAP query call and parse its reply."""
        service = self._get_client().service
        logger.debug(
            "UID query request: tid=%s, benid=%s, id=%s, uid_tn=%s, uid=%s, stufe=%d",
            mask_credential(credentials.tid),
            mask_credential(credentials.benid),
            mask_credential(session_id) if session_id else "?",
            request.uid_tn,
            request.uid,
            request.stufe,
        )
        reply = service.uidAbfrage(
            tid=credentials.tid,
            benid=credentials.benid,
            id=session_id,
            uid_tn=request.uid_tn,
            uid=request.uid,
            stufe=request.stufe,
        )
        parsed = _parse_query_response(reply)
        logger.debug(
            "UID query response: rc=%d, msg=%s, name=%s, address=%s",
            parsed.return_code,
            parsed.message,
            parsed.name,
            parsed.address.as_lines(),
        )
        return parsed

    def _process_query_response(
        self,
        session_id: str,
        credentials: FinanzOnlineCredentials,
        request: UidCheckRequest,
        parsed: SoapUidQueryResponse,
    ) -> UidCheckResult:
        """Turn the validated reply into a UidCheckResult or a SessionError."""
        if parsed.return_code == ReturnCode.SESSION_INVALID:
            diagnostics = _build_query_diagnostics(session_id, credentials, request, parsed)
            raise SessionError(f"Session invalid or expired: {parsed.message}", return_code=parsed.return_code, diagnostics=diagnostics)

        name: str = ""
        address: Address | None = None
        if parsed.return_code == ReturnCode.UID_VALID:
            name = parsed.name
            address = parsed.address
            logger.info("UID %s is valid: %s", request.uid, name)
        else:
            logger.info("UID %s verification returned code %d: %s", request.uid, parsed.return_code, parsed.message)

        return UidCheckResult(
            uid=request.uid,
            return_code=parsed.return_code,
            message=parsed.message,
            name=name,
            address=address,
            timestamp=datetime.now(timezone.utc),
        )
