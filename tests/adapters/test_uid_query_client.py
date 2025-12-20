# pyright: reportPrivateUsage=false
"""Tests for FinanzOnline UID query client adapter.

Tests cover UID query operations with mocked zeep SOAP client.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from zeep.exceptions import Fault, TransportError

from finanzonline_uid.adapters.finanzonline.uid_query_client import (
    FinanzOnlineQueryClient,
    UID_QUERY_SERVICE_WSDL,
)
from finanzonline_uid.domain.errors import QueryError, SessionError
from finanzonline_uid.domain.models import FinanzOnlineCredentials, UidCheckRequest


@pytest.fixture
def credentials() -> FinanzOnlineCredentials:
    """Test credentials fixture with XSD-compliant values."""
    return FinanzOnlineCredentials(
        tid="123456789",
        benid="TESTUSER",
        pin="testpin123",
        herstellerid="ATU12345678",
    )


@pytest.fixture
def uid_request() -> UidCheckRequest:
    """Test request fixture."""
    return UidCheckRequest(
        uid_tn="ATU12345678",
        uid="DE987654321",
        stufe=2,
    )


@pytest.fixture
def query_client() -> FinanzOnlineQueryClient:
    """Query client fixture."""
    return FinanzOnlineQueryClient(timeout=30.0)


class TestFinanzOnlineQueryClientInit:
    """Tests for query client initialization."""

    def test_init_default_timeout(self) -> None:
        """Should initialize with default timeout."""
        client = FinanzOnlineQueryClient()
        assert client._timeout == 30.0

    def test_init_custom_timeout(self) -> None:
        """Should accept custom timeout."""
        client = FinanzOnlineQueryClient(timeout=60.0)
        assert client._timeout == 60.0

    def test_client_starts_none(self) -> None:
        """Should start with no zeep client."""
        client = FinanzOnlineQueryClient()
        assert client._client is None


class TestGetClient:
    """Tests for lazy client initialization."""

    def test_creates_client_on_first_call(self, query_client: FinanzOnlineQueryClient) -> None:
        """Should create zeep Client on first call."""
        with patch("finanzonline_uid.adapters.finanzonline.uid_query_client.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            result = query_client._get_client()

            mock_client_class.assert_called_once_with(UID_QUERY_SERVICE_WSDL)
            assert result == mock_client

    def test_reuses_client_on_subsequent_calls(self, query_client: FinanzOnlineQueryClient) -> None:
        """Should reuse existing client."""
        with patch("finanzonline_uid.adapters.finanzonline.uid_query_client.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            result1 = query_client._get_client()
            result2 = query_client._get_client()

            mock_client_class.assert_called_once()  # Only one call
            assert result1 is result2


class TestQuery:
    """Tests for query method."""

    def test_query_valid_uid(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """Should return valid result with company info for valid UID."""
        mock_response = MagicMock()
        mock_response.rc = 0
        mock_response.msg = "UID is valid"
        mock_response.name = "Test Company GmbH"
        mock_response.adr_1 = "Test Company GmbH"
        mock_response.adr_2 = "Test Street 123"
        mock_response.adr_3 = "12345 Test City"
        mock_response.adr_4 = ""
        mock_response.adr_5 = ""
        mock_response.adr_6 = "DE"

        with patch.object(query_client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = query_client.query("SESSION123", credentials, uid_request)

            assert result.uid == "DE987654321"
            assert result.return_code == 0
            assert result.is_valid is True
            assert result.name == "Test Company GmbH"
            assert result.address is not None
            assert result.address.line1 == "Test Company GmbH"
            assert result.address.line2 == "Test Street 123"
            assert result.address.line3 == "12345 Test City"
            assert result.address.line6 == "DE"

            mock_client.service.uidAbfrage.assert_called_once_with(
                tid=credentials.tid,
                benid=credentials.benid,
                id="SESSION123",
                uid_tn=uid_request.uid_tn,
                uid=uid_request.uid,
                stufe=uid_request.stufe,
            )

    def test_query_invalid_uid(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """Should return invalid result for invalid UID."""
        mock_response = MagicMock()
        mock_response.rc = 1
        mock_response.msg = "UID is invalid"

        with patch.object(query_client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = query_client.query("SESSION123", credentials, uid_request)

            assert result.return_code == 1
            assert result.is_valid is False
            assert result.name == ""
            assert result.address is None

    def test_query_session_expired(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """Should raise SessionError for expired session."""
        mock_response = MagicMock()
        mock_response.rc = -1
        mock_response.msg = "Session expired"

        with patch.object(query_client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.return_value = mock_response
            mock_get_client.return_value = mock_client

            with pytest.raises(SessionError) as exc_info:
                query_client.query("SESSION123", credentials, uid_request)

            assert exc_info.value.return_code == -1
            assert "Session invalid or expired" in str(exc_info.value)

    def test_query_soap_fault(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """Should raise QueryError on SOAP fault."""
        with patch.object(query_client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.side_effect = Fault("SOAP error")
            mock_get_client.return_value = mock_client

            with pytest.raises(QueryError) as exc_info:
                query_client.query("SESSION123", credentials, uid_request)

            assert "SOAP fault" in str(exc_info.value)

    def test_query_transport_error(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """Should raise retryable QueryError on transport error."""
        with patch.object(query_client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.side_effect = TransportError("Connection failed")
            mock_get_client.return_value = mock_client

            with pytest.raises(QueryError) as exc_info:
                query_client.query("SESSION123", credentials, uid_request)

            assert "Connection error" in str(exc_info.value)
            assert exc_info.value.retryable is True

    def test_query_unexpected_error(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """Should wrap unexpected errors in QueryError."""
        with patch.object(query_client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.side_effect = RuntimeError("Unexpected")
            mock_get_client.return_value = mock_client

            with pytest.raises(QueryError) as exc_info:
                query_client.query("SESSION123", credentials, uid_request)

            assert "Unexpected error" in str(exc_info.value)

    def test_query_handles_none_msg(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """Should handle None message from response."""
        mock_response = MagicMock()
        mock_response.rc = 1
        mock_response.msg = None

        with patch.object(query_client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = query_client.query("SESSION123", credentials, uid_request)

            assert result.message == ""

    def test_query_handles_missing_name(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """Should handle missing name attribute for valid UID."""
        mock_response = MagicMock(spec=["rc", "msg"])  # No name attribute
        mock_response.rc = 0
        mock_response.msg = "UID valid"

        with patch.object(query_client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = query_client.query("SESSION123", credentials, uid_request)

            assert result.name == ""

    def test_query_handles_none_name(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """Should handle None name attribute for valid UID."""
        mock_response = MagicMock()
        mock_response.rc = 0
        mock_response.msg = "UID valid"
        mock_response.name = None
        mock_response.adr_1 = "Line 1"
        mock_response.adr_2 = ""
        mock_response.adr_3 = ""
        mock_response.adr_4 = ""
        mock_response.adr_5 = ""
        mock_response.adr_6 = ""

        with patch.object(query_client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = query_client.query("SESSION123", credentials, uid_request)

            assert result.name == ""

    def test_query_handles_none_address_lines(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """Should handle None address line attributes."""
        mock_response = MagicMock()
        mock_response.rc = 0
        mock_response.msg = "UID valid"
        mock_response.name = "Company"
        mock_response.adr_1 = None
        mock_response.adr_2 = None
        mock_response.adr_3 = None
        mock_response.adr_4 = None
        mock_response.adr_5 = None
        mock_response.adr_6 = None

        with patch.object(query_client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = query_client.query("SESSION123", credentials, uid_request)

            assert result.address is not None
            assert result.address.line1 == ""
            assert result.address.line2 == ""

    def test_query_various_return_codes(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """Should handle various return codes."""
        test_cases = [
            (4, "Wrong UID format"),
            (5, "Invalid requester UID"),
            (10, "Member state forbids query"),
            (1513, "Rate limit exceeded"),
        ]

        for return_code, message in test_cases:
            mock_response = MagicMock()
            mock_response.rc = return_code
            mock_response.msg = message

            with patch.object(query_client, "_get_client") as mock_get_client:
                mock_client = MagicMock()
                mock_client.service.uidAbfrage.return_value = mock_response
                mock_get_client.return_value = mock_client

                result = query_client.query("SESSION123", credentials, uid_request)

                assert result.return_code == return_code
                assert result.message == message
                assert result.is_valid is False

    def test_query_timestamp_is_utc(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """Should include UTC timestamp in result."""
        mock_response = MagicMock()
        mock_response.rc = 0
        mock_response.msg = "Valid"
        mock_response.name = "Company"
        mock_response.adr_1 = ""
        mock_response.adr_2 = ""
        mock_response.adr_3 = ""
        mock_response.adr_4 = ""
        mock_response.adr_5 = ""
        mock_response.adr_6 = ""

        with patch.object(query_client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = query_client.query("SESSION123", credentials, uid_request)

            assert result.timestamp is not None
            assert result.timestamp.tzinfo is not None
