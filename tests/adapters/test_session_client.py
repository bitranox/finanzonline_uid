# pyright: reportPrivateUsage=false
"""Session client adapter: every SOAP interaction a single verse.

Tests verify login/logout operations with the FinanzOnline session webservice.
SOAP calls are mocked because the real service requires live credentials and
network access - these are external dependencies we cannot control in tests.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from zeep.exceptions import Fault, TransportError

from finanzonline_uid.adapters.finanzonline._soap_common import MalformedSoapResponseError
from finanzonline_uid.adapters.finanzonline.session_client import (
    SESSION_SERVICE_WSDL,
    FinanzOnlineSessionClient,
    SoapLoginResponse,
    SoapLogoutResponse,
    _parse_login_response,
)
from finanzonline_uid.domain.errors import AuthenticationError, ServiceMaintenanceError, SessionError
from finanzonline_uid.domain.models import SoapOperation


def _login_reply(*, rc: object, msg: str | None = None, id: str | None = None) -> SimpleNamespace:
    """A loginResponse shaped like zeep's: every element present, an omitted one None."""
    return SimpleNamespace(rc=rc, msg=msg, id=id)


def _logout_reply(*, rc: object, msg: str | None = None) -> SimpleNamespace:
    """A logoutResponse shaped like zeep's: every element present, an omitted one None."""
    return SimpleNamespace(rc=rc, msg=msg)


def _client_answering(*, login: object = None, logout: object = None) -> tuple[FinanzOnlineSessionClient, MagicMock]:
    """A session client whose zeep service returns the given replies (or raises them if exceptions)."""
    client = FinanzOnlineSessionClient()
    zeep = MagicMock()
    for operation, reply in (("login", login), ("logout", logout)):
        method = getattr(zeep.service, operation)
        if isinstance(reply, BaseException):
            method.side_effect = reply
        else:
            method.return_value = reply
    client._client = zeep
    return client, zeep


# ============================================================================
# Initialization
# ============================================================================


@pytest.mark.os_agnostic
class TestClientInitialization:
    """The session client initializes with sensible defaults."""

    def test_default_timeout_is_thirty_seconds(self) -> None:
        """A fresh client uses 30 seconds as the default timeout."""
        client = FinanzOnlineSessionClient()
        assert client._timeout == 30.0

    def test_custom_timeout_is_accepted(self) -> None:
        """Custom timeout values are stored correctly."""
        client = FinanzOnlineSessionClient(timeout=60.0)
        assert client._timeout == 60.0

    def test_zeep_client_starts_as_none(self) -> None:
        """The underlying zeep client is lazily initialized."""
        client = FinanzOnlineSessionClient()
        assert client._client is None


# ============================================================================
# Lazy Client Creation
# ============================================================================


@pytest.mark.os_agnostic
class TestLazyClientCreation:
    """The zeep client is created on first use and reused thereafter."""

    def test_first_call_creates_zeep_client(self) -> None:
        """Calling _get_client creates the zeep Client."""
        client = FinanzOnlineSessionClient()
        with patch("finanzonline_uid.adapters.finanzonline.session_client.Client") as mock_class:
            mock_instance = MagicMock()
            mock_class.return_value = mock_instance

            result = client._get_client()

            mock_class.assert_called_once()
            call_args = mock_class.call_args
            assert call_args[0][0] == SESSION_SERVICE_WSDL
            assert "transport" in call_args[1]  # Transport is now passed
            assert result is mock_instance

    def test_subsequent_calls_reuse_existing_client(self) -> None:
        """Multiple calls return the same client instance."""
        client = FinanzOnlineSessionClient()
        with patch("finanzonline_uid.adapters.finanzonline.session_client.Client") as mock_class:
            mock_instance = MagicMock()
            mock_class.return_value = mock_instance

            first = client._get_client()
            second = client._get_client()

            mock_class.assert_called_once()
            assert first is second


# ============================================================================
# Login Success Scenarios
# ============================================================================


@pytest.mark.os_agnostic
class TestLoginSuccess:
    """Successful login returns a valid SessionInfo."""

    def test_returns_session_info_with_valid_credentials(
        self,
        valid_credentials: Any,
        mock_soap_login_response: MagicMock,
    ) -> None:
        """Valid credentials yield a populated SessionInfo."""
        client = FinanzOnlineSessionClient()
        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.login.return_value = mock_soap_login_response
            mock_get.return_value = mock_zeep

            result = client.login(valid_credentials)

            assert result.session_id == "SESSION123456"
            assert result.return_code == 0
            assert result.message == "Login successful"

    def test_passes_credentials_to_soap_service(
        self,
        valid_credentials: Any,
        mock_soap_login_response: MagicMock,
    ) -> None:
        """Credentials are forwarded to the SOAP login call."""
        client = FinanzOnlineSessionClient()
        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.login.return_value = mock_soap_login_response
            mock_get.return_value = mock_zeep

            client.login(valid_credentials)

            mock_zeep.service.login.assert_called_once_with(
                tid=valid_credentials.tid,
                benid=valid_credentials.benid,
                pin=valid_credentials.pin,
                herstellerid=valid_credentials.herstellerid,
            )


# ============================================================================
# Login Failure Scenarios
# ============================================================================


@pytest.mark.os_agnostic
class TestLoginFailure:
    """Login failures are handled gracefully with appropriate errors."""

    def test_non_zero_return_code_yields_failed_session_info(
        self,
        valid_credentials: Any,
    ) -> None:
        """Non-zero codes are returned in SessionInfo without raising."""
        client = FinanzOnlineSessionClient()
        response = MagicMock()
        response.rc = -3
        response.msg = "Technical error"
        response.id = ""

        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.login.return_value = response
            mock_get.return_value = mock_zeep

            result = client.login(valid_credentials)

            assert result.return_code == -3
            assert result.message == "Technical error"

    def test_code_minus_four_raises_authentication_error(
        self,
        valid_credentials: Any,
    ) -> None:
        """Return code -4 triggers an AuthenticationError."""
        client = FinanzOnlineSessionClient()
        response = _login_reply(rc=-4, msg="Not authorized")

        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.login.return_value = response
            mock_get.return_value = mock_zeep

            with pytest.raises(AuthenticationError) as exc_info:
                client.login(valid_credentials)

            assert exc_info.value.return_code == -4
            assert "Not authorized" in str(exc_info.value)

    def test_soap_fault_raises_session_error(
        self,
        valid_credentials: Any,
    ) -> None:
        """SOAP faults are wrapped in SessionError."""
        client = FinanzOnlineSessionClient()
        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.login.side_effect = Fault("SOAP error")
            mock_get.return_value = mock_zeep

            with pytest.raises(SessionError) as exc_info:
                client.login(valid_credentials)

            assert "SOAP fault" in str(exc_info.value)

    def test_transport_error_raises_session_error(
        self,
        valid_credentials: Any,
    ) -> None:
        """Transport errors are wrapped in SessionError."""
        client = FinanzOnlineSessionClient()
        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.login.side_effect = TransportError("Connection failed")
            mock_get.return_value = mock_zeep

            with pytest.raises(SessionError) as exc_info:
                client.login(valid_credentials)

            assert "Connection error" in str(exc_info.value)

    def test_unexpected_error_raises_session_error(
        self,
        valid_credentials: Any,
    ) -> None:
        """Unexpected exceptions are wrapped in SessionError."""
        client = FinanzOnlineSessionClient()
        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.login.side_effect = RuntimeError("Unexpected")
            mock_get.return_value = mock_zeep

            with pytest.raises(SessionError) as exc_info:
                client.login(valid_credentials)

            assert "Unexpected error" in str(exc_info.value)

    def test_html_maintenance_page_raises_service_maintenance_error(
        self,
        valid_credentials: Any,
    ) -> None:
        """HTML maintenance page triggers ServiceMaintenanceError (retryable)."""
        client = FinanzOnlineSessionClient()
        xml_error = Exception("Invalid XML content received (Opening and ending tag mismatch: link line 10 and head, line 11, column 8)")
        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.login.side_effect = xml_error
            mock_get.return_value = mock_zeep

            with pytest.raises(ServiceMaintenanceError) as exc_info:
                client.login(valid_credentials)

            assert exc_info.value.retryable is True
            assert "maintenance" in str(exc_info.value).lower()


# ============================================================================
# Login Edge Cases
# ============================================================================


@pytest.mark.os_agnostic
class TestLoginEdgeCases:
    """Edge cases in SOAP responses are handled gracefully."""

    def test_none_message_becomes_empty_string(
        self,
        valid_credentials: Any,
    ) -> None:
        """A None message in the response becomes an empty string."""
        client = FinanzOnlineSessionClient()
        response = MagicMock()
        response.rc = 0
        response.msg = None
        response.id = "SESSION123"

        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.login.return_value = response
            mock_get.return_value = mock_zeep

            result = client.login(valid_credentials)

            assert result.message == ""

    def test_missing_id_attribute_becomes_empty_string(
        self,
        valid_credentials: Any,
    ) -> None:
        """A response without 'id' attribute uses empty string."""
        client = FinanzOnlineSessionClient()
        response = MagicMock(spec=["rc", "msg"])
        response.rc = 0
        response.msg = "Success"

        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.login.return_value = response
            mock_get.return_value = mock_zeep

            result = client.login(valid_credentials)

            assert result.session_id == ""


# ============================================================================
# Logout Success Scenarios
# ============================================================================


@pytest.mark.os_agnostic
class TestLogoutSuccess:
    """Successful logout returns True."""

    def test_returns_true_on_successful_logout(
        self,
        valid_credentials: Any,
    ) -> None:
        """Return code 0 means logout succeeded."""
        client = FinanzOnlineSessionClient()
        response = _logout_reply(rc=0)

        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.logout.return_value = response
            mock_get.return_value = mock_zeep

            result = client.logout("SESSION123", valid_credentials)

            assert result is True

    def test_passes_session_id_to_soap_service(
        self,
        valid_credentials: Any,
    ) -> None:
        """Session ID is forwarded to the SOAP logout call."""
        client = FinanzOnlineSessionClient()
        response = _logout_reply(rc=0)

        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.logout.return_value = response
            mock_get.return_value = mock_zeep

            client.logout("SESSION123", valid_credentials)

            mock_zeep.service.logout.assert_called_once_with(
                tid=valid_credentials.tid,
                benid=valid_credentials.benid,
                id="SESSION123",
            )


# ============================================================================
# Logout Failure Scenarios
# ============================================================================


@pytest.mark.os_agnostic
class TestLogoutFailure:
    """Logout failures return False without raising exceptions."""

    def test_non_zero_code_returns_false(
        self,
        valid_credentials: Any,
    ) -> None:
        """Non-zero return codes mean logout failed."""
        client = FinanzOnlineSessionClient()
        response = _logout_reply(rc=-1)

        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.logout.return_value = response
            mock_get.return_value = mock_zeep

            result = client.logout("SESSION123", valid_credentials)

            assert result is False

    def test_transport_error_returns_false(
        self,
        valid_credentials: Any,
    ) -> None:
        """Transport errors return False (logout is non-fatal)."""
        client = FinanzOnlineSessionClient()
        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.logout.side_effect = TransportError("Connection lost")
            mock_get.return_value = mock_zeep

            result = client.logout("SESSION123", valid_credentials)

            assert result is False

    def test_missing_rc_attribute_returns_false(
        self,
        valid_credentials: Any,
    ) -> None:
        """A response without 'rc' attribute returns False."""
        client = FinanzOnlineSessionClient()
        response = MagicMock(spec=[])

        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.logout.return_value = response
            mock_get.return_value = mock_zeep

            result = client.logout("SESSION123", valid_credentials)

            assert result is False


# ============================================================================
# Logout Edge Cases
# ============================================================================


@pytest.mark.os_agnostic
class TestLogoutEdgeCases:
    """Edge cases in logout are handled gracefully."""

    def test_short_session_id_is_handled(
        self,
        valid_credentials: Any,
    ) -> None:
        """Short session IDs don't break logging."""
        client = FinanzOnlineSessionClient()
        response = _logout_reply(rc=0)

        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.logout.return_value = response
            mock_get.return_value = mock_zeep

            result = client.logout("ABC", valid_credentials)

            assert result is True

    def test_empty_session_id_is_handled(
        self,
        valid_credentials: Any,
    ) -> None:
        """Empty session IDs don't cause errors."""
        client = FinanzOnlineSessionClient()
        response = _logout_reply(rc=0)

        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.logout.return_value = response
            mock_get.return_value = mock_zeep

            result = client.logout("", valid_credentials)

            assert result is True


# ============================================================================
# Reply parsing (the zeep boundary)
# ============================================================================


@pytest.mark.os_agnostic
class TestReplyParsing:
    """A zeep reply is parsed once into a validated record."""

    def test_login_reply_maps_none_text_to_empty(self) -> None:
        """Omitted msg/id (zeep gives None) read as empty strings."""
        parsed = _parse_login_response(_login_reply(rc=-3))

        assert parsed == SoapLoginResponse.model_validate(SimpleNamespace(rc=-3, msg="", id=""))
        assert (parsed.return_code, parsed.message, parsed.session_id) == (-3, "", "")

    def test_login_reply_without_attributes_uses_defaults(self) -> None:
        """A reply object lacking msg and id still parses."""
        parsed = _parse_login_response(SimpleNamespace(rc=0))

        assert (parsed.return_code, parsed.message, parsed.session_id) == (0, "", "")

    def test_login_reply_with_non_integer_rc_is_refused_by_field(self) -> None:
        """A non-integer rc names the field, never the reply's session id."""
        with pytest.raises(MalformedSoapResponseError) as exc_info:
            _parse_login_response(_login_reply(rc="abc", id="SESSIONSECRET42"))

        message = str(exc_info.value)
        assert message.startswith("Malformed login response: rc: ")
        assert "SESSIONSECRET42" not in message
        assert exc_info.value.__context__ is None

    def test_logout_reply_without_rc_has_no_return_code(self) -> None:
        """A logout reply without rc parses with return_code None."""
        assert SoapLogoutResponse.model_validate(SimpleNamespace()).return_code is None


@pytest.mark.os_agnostic
class TestMalformedReplies:
    """A reply that does not fit its record becomes the domain error, not a bare ValueError."""

    def test_login_with_non_integer_rc_raises_session_error(self, valid_credentials: Any) -> None:
        """A non-integer rc goes the unexpected-error path as SessionError."""
        client, _ = _client_answering(login=_login_reply(rc="abc", msg="x", id="SESSION123456"))

        with pytest.raises(SessionError) as exc_info:
            client.login(valid_credentials)

        assert str(exc_info.value).startswith("Unexpected error: Malformed login response: rc: ")
        assert isinstance(exc_info.value.__cause__, MalformedSoapResponseError)
        assert exc_info.value.retryable is False
        assert exc_info.value.diagnostics is not None
        assert exc_info.value.diagnostics.operation == SoapOperation.LOGIN
        assert exc_info.value.diagnostics.return_code == ""

    def test_logout_with_non_integer_rc_returns_false(self, valid_credentials: Any) -> None:
        """Logout stays non-fatal for a malformed reply."""
        client, _ = _client_answering(logout=_logout_reply(rc="abc"))

        assert client.logout("SESSION123", valid_credentials) is False

    def test_login_with_non_string_msg_raises_session_error(self, valid_credentials: Any) -> None:
        """A msg that is not a string is refused, never converted with str()."""
        client, _ = _client_answering(login=SimpleNamespace(rc=0, msg=123, id="SESSION123456"))

        with pytest.raises(SessionError) as exc_info:
            client.login(valid_credentials)

        assert str(exc_info.value).startswith("Unexpected error: Malformed login response: msg: ")
        assert isinstance(exc_info.value.__cause__, MalformedSoapResponseError)

    def test_login_reply_without_rc_raises_session_error(self, valid_credentials: Any) -> None:
        """A reply carrying no return code is refused, never read as a successful login."""
        client, _ = _client_answering(login=SimpleNamespace(msg="x", id="SESSION123456"))

        with pytest.raises(SessionError) as exc_info:
            client.login(valid_credentials)

        assert str(exc_info.value).startswith("Unexpected error: Malformed login response: rc: Field required")

    def test_login_with_no_reply_names_the_whole_reply(self, valid_credentials: Any) -> None:
        """A None reply is refused as a whole, not as an empty field name."""
        client, _ = _client_answering(login=None)

        with pytest.raises(SessionError) as exc_info:
            client.login(valid_credentials)

        assert str(exc_info.value).startswith("Unexpected error: Malformed login response: (whole reply): ")


@pytest.mark.os_agnostic
class TestLoginDiagnosticsAndLogging:
    """Diagnostics carry the parsed reply; logs keep credentials masked."""

    def test_authentication_error_diagnostics_hold_parsed_reply(self, valid_credentials: Any) -> None:
        """The -4 diagnostics carry operation, return code, message and a masked session id."""
        client, _ = _client_answering(login=_login_reply(rc=-4, msg="Not authorized", id="SESSION123456"))

        with pytest.raises(AuthenticationError) as exc_info:
            client.login(valid_credentials)

        diagnostics = exc_info.value.diagnostics
        assert diagnostics is not None
        assert diagnostics.operation == SoapOperation.LOGIN
        assert diagnostics.return_code == "-4"
        assert diagnostics.response_message == "Not authorized"
        assert diagnostics.session_id == "SESS...3456"
        assert diagnostics.pin == "test...n123"

    def test_soap_fault_message_is_the_fault_text(self, valid_credentials: Any) -> None:
        """The SessionError reads 'SOAP fault: <fault message>'."""
        client, _ = _client_answering(login=Fault("Server busy"))

        with pytest.raises(SessionError) as exc_info:
            client.login(valid_credentials)

        assert str(exc_info.value) == "SOAP fault: Server busy"

    def test_login_debug_log_masks_credentials_and_session_id(self, valid_credentials: Any, caplog: pytest.LogCaptureFixture) -> None:
        """tid, benid, pin and the session id never reach the log in clear text."""
        client, _ = _client_answering(login=_login_reply(rc=0, msg="ok", id="SESSION123456"))

        with caplog.at_level(logging.DEBUG, logger="finanzonline_uid.adapters.finanzonline.session_client"):
            client.login(valid_credentials)

        text = caplog.text
        for secret in (valid_credentials.tid, valid_credentials.benid, valid_credentials.pin, "SESSION123456"):
            assert secret not in text
        assert valid_credentials.herstellerid in text
        assert "SESS...3456" in text

    def test_logout_debug_log_masks_credentials_and_session_id(self, valid_credentials: Any, caplog: pytest.LogCaptureFixture) -> None:
        """The logout request log masks tid, benid and the session id."""
        client, _ = _client_answering(logout=_logout_reply(rc=0))

        with caplog.at_level(logging.DEBUG, logger="finanzonline_uid.adapters.finanzonline.session_client"):
            client.logout("SESSION123456", valid_credentials)

        text = caplog.text
        for secret in (valid_credentials.tid, valid_credentials.benid, "SESSION123456"):
            assert secret not in text
