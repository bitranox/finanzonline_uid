"""FinanzOnline session management adapter.

Purpose
-------
Implement SessionPort for authentication with BMF FinanzOnline
session webservice using SOAP/zeep.

Contents
--------
* :class:`FinanzOnlineSessionClient` - Session login/logout adapter
* :class:`SoapLoginResponse` - Validated login reply
* :class:`SoapLogoutResponse` - Validated logout reply

System Role
-----------
Adapters layer - SOAP client for FinanzOnline session webservice.

Reference
---------
BMF Session Webservice: https://finanzonline.bmf.gv.at/fon/ws/sessionService.wsdl
"""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import TYPE_CHECKING, Protocol, cast

from pydantic import BaseModel, Field, ValidationError
from zeep import Client
from zeep.exceptions import Fault, TransportError
from zeep.transports import Transport

from finanzonline_uid.adapters.finanzonline._soap_common import (
    MalformedSoapResponseError,
    SoapText,
    TransportFactory,
    describe_validation_error,
    mask_credential,
)
from finanzonline_uid.domain.errors import AuthenticationError, ServiceMaintenanceError, SessionError
from finanzonline_uid.domain.models import Diagnostics, SessionInfo, SoapOperation
from finanzonline_uid.domain.return_codes import ReturnCode
from finanzonline_uid.domain.soap_utils import extract_text_from_html_error, is_html_response_error

if TYPE_CHECKING:
    from finanzonline_uid.domain.models import FinanzOnlineCredentials


__all__ = [
    "SESSION_SERVICE_WSDL",
    "FinanzOnlineSessionClient",
    "SoapLoginResponse",
    "SoapLogoutResponse",
]


logger = logging.getLogger(__name__)


SESSION_SERVICE_WSDL = "https://finanzonline.bmf.gv.at/fonws/ws/sessionService.wsdl"


class _SessionReturnCode(IntEnum):
    """Session-webservice return codes ReturnCode has no session-scoped member for.

    BMF Session Webservice documentation, section 4 "Return Codes": 0 means
    the call succeeded. ReturnCode's 0 is UID_VALID, a UID-query meaning, so
    logout compares against this member instead. Login's -4 is
    ReturnCode.NOT_AUTHORIZED, which means the same for both services.
    """

    OK = 0


class _SessionService(Protocol):
    """The two session operations zeep builds from the WSDL at run time."""

    def login(self, *, tid: str, benid: str, pin: str, herstellerid: str) -> object:
        """Send loginRequest; the reply is validated by :class:`SoapLoginResponse`."""
        ...

    def logout(self, *, tid: str, benid: str, id: str) -> object:
        """Send logoutRequest; the reply is validated by :class:`SoapLogoutResponse`."""
        ...


class _SessionSoapClient(Protocol):
    """The part of a zeep ``Client`` this adapter uses."""

    @property
    def service(self) -> _SessionService:
        """Service proxy bound to the WSDL's default port."""
        ...


class SoapLoginResponse(BaseModel, frozen=True, from_attributes=True):
    """Validated login reply from FinanzOnline (loginResponse in login.xsd).

    Attributes:
        return_code: Integer return code from BMF (0 = success, -4 = auth failure).
        message: Response message from BMF ("" when omitted).
        session_id: Session identifier ("" if login failed).

    Examples:
        >>> from types import SimpleNamespace
        >>> reply = SoapLoginResponse.model_validate(SimpleNamespace(rc=0, msg=None, id="SESSION123456"))
        >>> (reply.return_code, reply.message, reply.masked_session_id())
        (0, '', 'SESS...3456')
    """

    # Required: login.xsd declares rc without minOccurs="0", and reading a missing
    # code as 0 would report a reply that carries no answer as a successful login.
    return_code: int = Field(validation_alias="rc")
    message: SoapText = Field(default="", validation_alias="msg")
    session_id: SoapText = Field(default="", validation_alias="id")

    def masked_session_id(self) -> str:
        """Return masked session ID for logging."""
        if not self.session_id:
            return ""
        return mask_credential(self.session_id)


class SoapLogoutResponse(BaseModel, frozen=True, from_attributes=True):
    """Validated logout reply from FinanzOnline (logoutResponse in login.xsd).

    Attributes:
        return_code: Integer return code from BMF, None when the reply carries none.
        message: Response message from BMF ("" when omitted).

    Examples:
        >>> from types import SimpleNamespace
        >>> SoapLogoutResponse.model_validate(SimpleNamespace(rc=0, msg="ok")).return_code
        0
    """

    return_code: int | None = Field(default=None, validation_alias="rc")
    message: SoapText = Field(default="", validation_alias="msg")


def _parse_login_response(reply: object) -> SoapLoginResponse:
    """Parse a zeep login reply once into its validated record.

    Args:
        reply: The object zeep returned for loginRequest.

    Returns:
        The validated record.

    Raises:
        MalformedSoapResponseError: When a field does not fit (a non-integer rc).
    """
    try:
        return SoapLoginResponse.model_validate(reply)
    except ValidationError as exc:
        problems = describe_validation_error(exc)
    # Raised outside the except block so the ValidationError, which holds the
    # reply (and its session id), does not ride along as __context__.
    raise MalformedSoapResponseError(f"Malformed login response: {problems}")


def _parse_logout_response(reply: object) -> SoapLogoutResponse:
    """Parse a zeep logout reply once into its validated record.

    Args:
        reply: The object zeep returned for logoutRequest.

    Returns:
        The validated record.

    Raises:
        MalformedSoapResponseError: When a field does not fit (a non-integer rc).
    """
    try:
        return SoapLogoutResponse.model_validate(reply)
    except ValidationError as exc:
        problems = describe_validation_error(exc)
    raise MalformedSoapResponseError(f"Malformed logout response: {problems}")


def _build_login_diagnostics(
    credentials: FinanzOnlineCredentials,
    parsed: SoapLoginResponse | None = None,
    error: str = "",
) -> Diagnostics:
    """Build diagnostic information for login operation.

    Args:
        credentials: The credentials used (the PIN is masked).
        parsed: The validated reply, if one was received and parsed.
        error: Optional error message.

    Returns:
        Diagnostics object with diagnostic information.
    """
    return Diagnostics(
        operation=SoapOperation.LOGIN,
        tid=credentials.tid,
        benid=credentials.benid,
        pin=mask_credential(credentials.pin),
        session_id="" if parsed is None else parsed.masked_session_id(),
        return_code="" if parsed is None else str(parsed.return_code),
        response_message="" if parsed is None else parsed.message,
        error_detail=error,
    )


def _login_error(
    exc: Exception,
    credentials: FinanzOnlineCredentials,
    parsed: SoapLoginResponse | None,
) -> SessionError:
    """Translate a failure during login into the domain error to raise.

    Args:
        exc: The exception that occurred (never a domain error: those propagate as they are).
        credentials: FinanzOnline credentials.
        parsed: The validated reply, if parsing got that far.

    Returns:
        ServiceMaintenanceError when BMF answered with an HTML maintenance page,
        otherwise a SessionError naming the failure.
    """
    diagnostics = _build_login_diagnostics(credentials, parsed, error=str(exc))

    if isinstance(exc, Fault):
        logger.error("SOAP fault during login: %s", exc)
        # str(Fault) is Fault.message (zeep passes it to Exception.__init__); reading
        # .message directly would go through zeep's untyped attribute.
        return SessionError(f"SOAP fault: {exc}", diagnostics=diagnostics)

    if isinstance(exc, TransportError):
        logger.error("Transport error during login: %s", exc)
        return SessionError(f"Connection error: {exc}", diagnostics=diagnostics)

    if is_html_response_error(exc):
        message = extract_text_from_html_error(exc)
        logger.warning("FinanzOnline returned HTML instead of SOAP XML (likely maintenance): %s", exc)
        return ServiceMaintenanceError(message, diagnostics=diagnostics)

    logger.error("Unexpected error during login: %s", exc)
    return SessionError(f"Unexpected error: {exc}", diagnostics=diagnostics)


class FinanzOnlineSessionClient:
    """SOAP client for FinanzOnline session management.

    Implements SessionPort protocol for login/logout operations
    with the BMF session webservice.

    Attributes:
        _timeout: Request timeout in seconds.
        _client: Zeep SOAP client (lazy-initialized).
    """

    def __init__(self, timeout: float = 30.0) -> None:
        """Initialize session client.

        Args:
            timeout: Request timeout in seconds.
        """
        self._timeout = timeout
        self._client: _SessionSoapClient | None = None

    def _get_client(self) -> _SessionSoapClient:
        """Get or create SOAP client.

        Returns:
            Zeep Client instance for session service.
        """
        if self._client is None:
            logger.debug("Creating session service client with timeout=%s", self._timeout)
            transport = cast("TransportFactory", Transport)(timeout=self._timeout, operation_timeout=self._timeout)
            # zeep builds `service` from the WSDL at run time, so nothing about it is
            # typed; this cast is the one place the adapter states what it relies on.
            self._client = cast("_SessionSoapClient", Client(SESSION_SERVICE_WSDL, transport=transport))
        return self._client

    def login(self, credentials: FinanzOnlineCredentials) -> SessionInfo:
        """Authenticate with FinanzOnline and obtain a session.

        Args:
            credentials: FinanzOnline credentials (tid, benid, pin).

        Returns:
            SessionInfo with session_id if successful.

        Raises:
            AuthenticationError: If credentials are invalid (code -4).
            SessionError: If session creation fails for other reasons.
        """
        logger.debug("Attempting login for tid=%s, benid=%s", mask_credential(credentials.tid), mask_credential(credentials.benid))
        parsed: SoapLoginResponse | None = None

        try:
            parsed = self._execute_login(credentials)
            return self._process_login_response(credentials, parsed)
        except (AuthenticationError, SessionError):
            # Raised by this client with its own diagnostics already.
            raise
        except Exception as exc:
            raise _login_error(exc, credentials, parsed) from exc

    def _execute_login(self, credentials: FinanzOnlineCredentials) -> SoapLoginResponse:
        """Execute the SOAP login call and parse its reply."""
        service = self._get_client().service
        logger.debug(
            "Login request: tid=%s, benid=%s, pin=%s, herstellerid=%s",
            mask_credential(credentials.tid),
            mask_credential(credentials.benid),
            mask_credential(credentials.pin),
            credentials.herstellerid,
        )
        reply = service.login(
            tid=credentials.tid,
            benid=credentials.benid,
            pin=credentials.pin,
            herstellerid=credentials.herstellerid,
        )
        parsed = _parse_login_response(reply)
        logger.debug("Login response: rc=%d, msg=%s, id=%s", parsed.return_code, parsed.message, parsed.masked_session_id())
        return parsed

    def _process_login_response(self, credentials: FinanzOnlineCredentials, parsed: SoapLoginResponse) -> SessionInfo:
        """Turn the validated login reply into a SessionInfo or an AuthenticationError."""
        if parsed.return_code == ReturnCode.NOT_AUTHORIZED:
            diagnostics = _build_login_diagnostics(credentials, parsed)
            raise AuthenticationError(f"Not authorized: {parsed.message}", return_code=parsed.return_code, diagnostics=diagnostics)

        return SessionInfo(session_id=parsed.session_id, return_code=parsed.return_code, message=parsed.message)

    def logout(self, session_id: str, credentials: FinanzOnlineCredentials) -> bool:
        """End a FinanzOnline session.

        Args:
            session_id: Active session identifier.
            credentials: FinanzOnline credentials.

        Returns:
            True if logout succeeded, False otherwise.
        """
        logger.debug(
            "Logout request: tid=%s, benid=%s, id=%s",
            mask_credential(credentials.tid),
            mask_credential(credentials.benid),
            mask_credential(session_id) if session_id else "?",
        )

        try:
            reply = self._get_client().service.logout(
                tid=credentials.tid,
                benid=credentials.benid,
                id=session_id,
            )
            parsed = _parse_logout_response(reply)
        except Exception as e:  # noqa: BLE001 - logout failures are non-fatal, just log and return False
            logger.warning("Logout failed (non-fatal): %s", e)
            return False

        logger.debug("Logout response: rc=%s, msg=%s", parsed.return_code, parsed.message)
        return parsed.return_code == _SessionReturnCode.OK
