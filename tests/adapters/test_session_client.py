# pyright: reportPrivateUsage=false
"""Session client adapter: every SOAP interaction a single verse.

Tests verify login/logout operations with the FinanzOnline session webservice.
SOAP calls are mocked because the real service requires live credentials and
network access - these are external dependencies we cannot control in tests.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from zeep.exceptions import Fault, TransportError

from uid_check_austria.adapters.finanzonline.session_client import (
    SESSION_SERVICE_WSDL,
    FinanzOnlineSessionClient,
)
from uid_check_austria.domain.errors import AuthenticationError, SessionError


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
        with patch("uid_check_austria.adapters.finanzonline.session_client.Client") as mock_class:
            mock_instance = MagicMock()
            mock_class.return_value = mock_instance

            result = client._get_client()

            mock_class.assert_called_once_with(SESSION_SERVICE_WSDL)
            assert result is mock_instance

    def test_subsequent_calls_reuse_existing_client(self) -> None:
        """Multiple calls return the same client instance."""
        client = FinanzOnlineSessionClient()
        with patch("uid_check_austria.adapters.finanzonline.session_client.Client") as mock_class:
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
        response = MagicMock()
        response.rc = -4
        response.msg = "Not authorized"

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
        response = MagicMock()
        response.rc = 0

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
        response = MagicMock()
        response.rc = 0

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
        response = MagicMock()
        response.rc = -1

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
        response = MagicMock()
        response.rc = 0

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
        response = MagicMock()
        response.rc = 0

        with patch.object(client, "_get_client") as mock_get:
            mock_zeep = MagicMock()
            mock_zeep.service.logout.return_value = response
            mock_get.return_value = mock_zeep

            result = client.logout("", valid_credentials)

            assert result is True
