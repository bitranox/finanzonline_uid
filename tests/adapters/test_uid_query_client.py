# pyright: reportPrivateUsage=false
"""Tests for FinanzOnline UID query client adapter.

Tests cover UID query operations with mocked zeep SOAP client.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from zeep.exceptions import Fault, TransportError

from finanzonline_uid.adapters.finanzonline._soap_common import MalformedSoapResponseError
from finanzonline_uid.adapters.finanzonline.uid_query_client import (
    UID_QUERY_SERVICE_WSDL,
    FinanzOnlineQueryClient,
    SoapUidQueryResponse,
    _capture_raw_response,
    _parse_query_response,
)
from finanzonline_uid.domain.errors import QueryError, ServiceMaintenanceError, SessionError
from finanzonline_uid.domain.models import Address, FinanzOnlineCredentials, SoapOperation, UidCheckRequest


def _uid_reply(*, rc: object, msg: str | None = None, name: str | None = None) -> SimpleNamespace:
    """A uidAbfrage reply shaped like zeep's: every element present, an omitted one None."""
    return SimpleNamespace(rc=rc, msg=msg, name=name, adrz1=None, adrz2=None, adrz3=None, adrz4=None, adrz5=None, adrz6=None)


def _client_answering(reply: object) -> tuple[FinanzOnlineQueryClient, MagicMock]:
    """A query client whose zeep service returns the given reply."""
    client = FinanzOnlineQueryClient()
    zeep = MagicMock()
    zeep.service.uidAbfrage.return_value = reply
    client._client = zeep
    return client, zeep


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

            mock_client_class.assert_called_once()
            call_args = mock_client_class.call_args
            assert call_args[0][0] == UID_QUERY_SERVICE_WSDL
            assert "transport" in call_args[1]  # Transport is now passed
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
        mock_response.adrz1 = "Test Company GmbH"
        mock_response.adrz2 = "Test Street 123"
        mock_response.adrz3 = "12345 Test City"
        mock_response.adrz4 = ""
        mock_response.adrz5 = ""
        mock_response.adrz6 = "DE"

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
        mock_response = _uid_reply(rc=1, msg="UID is invalid")

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
        mock_response = _uid_reply(rc=-1, msg="Session expired")

        with patch.object(query_client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.return_value = mock_response
            mock_get_client.return_value = mock_client

            with pytest.raises(SessionError) as exc_info:
                query_client.query("SESSION123", credentials, uid_request)

            assert exc_info.value.return_code == -1
            assert "Session invalid or expired" in str(exc_info.value)
            assert exc_info.value.diagnostics is not None
            assert exc_info.value.diagnostics.operation == SoapOperation.UID_QUERY
            assert exc_info.value.diagnostics.return_code == "-1"
            assert exc_info.value.diagnostics.response_message == "Session expired"

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

    def test_query_html_maintenance_page_raises_service_maintenance_error(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """HTML maintenance page triggers ServiceMaintenanceError (retryable)."""
        xml_error = Exception("Invalid XML content received (Opening and ending tag mismatch: link line 10 and head, line 11, column 8)")
        with patch.object(query_client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.side_effect = xml_error
            mock_get_client.return_value = mock_client

            with pytest.raises(ServiceMaintenanceError) as exc_info:
                query_client.query("SESSION123", credentials, uid_request)

            assert exc_info.value.retryable is True
            assert "maintenance" in str(exc_info.value).lower()

    def test_query_zeep_parsing_error_is_retryable(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """zeep TypeError 'name cannot be None' is wrapped as a retryable QueryError."""
        zeep_error = TypeError("name cannot be None", object)
        with patch.object(query_client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.side_effect = zeep_error
            mock_get_client.return_value = mock_client

            with pytest.raises(QueryError) as exc_info:
                query_client.query("SESSION123", credentials, uid_request)

            assert exc_info.value.retryable is True
            assert "malformed" in str(exc_info.value).lower()

    def test_query_zeep_parsing_error_includes_raw_response(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """Raw response captured by HistoryPlugin is included in diagnostics on parsing error."""
        captured_xml = "<Envelope><Body><Garbage>oops</Garbage></Body></Envelope>"
        zeep_error = TypeError("name cannot be None", object)
        with (
            patch("finanzonline_uid.adapters.finanzonline.uid_query_client._capture_raw_response", return_value=captured_xml),
            patch.object(query_client, "_get_client") as mock_get_client,
        ):
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.side_effect = zeep_error
            mock_get_client.return_value = mock_client

            with pytest.raises(QueryError) as exc_info:
                query_client.query("SESSION123", credentials, uid_request)

            assert exc_info.value.diagnostics is not None
            assert exc_info.value.diagnostics.raw_response == captured_xml

    def test_query_handles_none_msg(
        self,
        query_client: FinanzOnlineQueryClient,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
    ) -> None:
        """Should handle None message from response."""
        mock_response = _uid_reply(rc=1, msg=None)

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
        mock_response.adrz1 = "Line 1"
        mock_response.adrz2 = ""
        mock_response.adrz3 = ""
        mock_response.adrz4 = ""
        mock_response.adrz5 = ""
        mock_response.adrz6 = ""

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
        mock_response.adrz1 = None
        mock_response.adrz2 = None
        mock_response.adrz3 = None
        mock_response.adrz4 = None
        mock_response.adrz5 = None
        mock_response.adrz6 = None

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
            mock_response = _uid_reply(rc=return_code, msg=message)

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
        mock_response.adrz1 = ""
        mock_response.adrz2 = ""
        mock_response.adrz3 = ""
        mock_response.adrz4 = ""
        mock_response.adrz5 = ""
        mock_response.adrz6 = ""

        with patch.object(query_client, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.service.uidAbfrage.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = query_client.query("SESSION123", credentials, uid_request)

            assert result.timestamp is not None
            assert result.timestamp.tzinfo is not None


class TestCaptureRawResponse:
    """Tests for the raw-response capture helper used by failure diagnostics."""

    def test_returns_xml_when_response_envelope_present(self) -> None:
        """A populated last_received envelope is serialized to XML."""
        history = MagicMock()
        history.last_received = {"envelope": MagicMock(), "http_headers": {}}
        history.last_sent = None

        with patch("lxml.etree.tostring", return_value="<Envelope>response</Envelope>"):
            result = _capture_raw_response(history)

        assert "<Envelope>" in result
        assert "response" in result

    def test_falls_back_to_sent_marker_when_only_request_present(self) -> None:
        """If only the request envelope is captured, return a non-credential marker."""
        history = MagicMock()
        history.last_received = None
        history.last_sent = {"envelope": MagicMock(), "http_headers": {}}

        with patch("lxml.etree.tostring", return_value="<Envelope>secret-request-body</Envelope>"):
            result = _capture_raw_response(history)

        assert "Request was sent" in result
        # The actual request body must NOT leak - it contains credentials.
        assert "secret-request-body" not in result

    def test_returns_placeholder_when_buffer_empty(self) -> None:
        """When no envelope was ever captured, return a clear placeholder."""
        history = MagicMock()
        type(history).last_received = property(lambda self: (_ for _ in ()).throw(IndexError()))
        type(history).last_sent = property(lambda self: (_ for _ in ()).throw(IndexError()))

        result = _capture_raw_response(history)

        assert "No SOAP envelope captured" in result

    @pytest.mark.parametrize("odd_entry", [{"http_headers": {}}, {}, "not an entry", 42])
    def test_entry_without_envelope_reads_as_nothing_captured(self, odd_entry: object) -> None:
        """An entry lacking the envelope key, or not a mapping, never raises."""
        history = MagicMock()
        history.last_received = odd_entry
        history.last_sent = odd_entry

        result = _capture_raw_response(history)

        assert "No SOAP envelope captured" in result

    def test_truncates_oversized_responses(self) -> None:
        """Large envelopes are truncated to ~8 KB to keep emails reasonable."""
        big_xml = "<Envelope>" + ("x" * 20000) + "</Envelope>"
        history = MagicMock()
        history.last_received = {"envelope": MagicMock(), "http_headers": {}}

        with patch("lxml.etree.tostring", return_value=big_xml):
            result = _capture_raw_response(history)

        assert "[truncated]" in result
        assert len(result) < 9000  # 8192 cap + small header


class TestReplyParsing:
    """A zeep uidAbfrage reply is parsed once into a validated record."""

    def test_address_lines_come_from_adrz_attributes(self) -> None:
        """adrz1..adrz6 map to line1..line6; None reads as empty."""
        reply = SimpleNamespace(rc=0, msg="ok", name="ACME", adrz1="Street 1", adrz2=None, adrz3="1010 Wien", adrz4=None, adrz5=None, adrz6="AT")

        parsed = _parse_query_response(reply)

        assert parsed.address == Address(line1="Street 1", line3="1010 Wien", line6="AT")
        assert parsed.name == "ACME"

    def test_reply_lacking_optional_attributes_uses_defaults(self) -> None:
        """A reply object with only rc and msg parses with empty name and address."""
        parsed = SoapUidQueryResponse.model_validate(SimpleNamespace(rc=1, msg="invalid"))

        assert (parsed.return_code, parsed.message, parsed.name, parsed.address) == (1, "invalid", "", Address())

    def test_non_integer_rc_is_refused_by_field(self) -> None:
        """A non-integer rc names the field, not the reply content."""
        with pytest.raises(MalformedSoapResponseError) as exc_info:
            _parse_query_response(_uid_reply(rc="abc", name="SECRET COMPANY"))

        message = str(exc_info.value)
        assert message.startswith("Malformed uidAbfrage response: rc: ")
        assert "SECRET COMPANY" not in message
        assert exc_info.value.__context__ is None


class TestMalformedReply:
    """A reply that does not fit its record becomes a QueryError, not a bare ValueError."""

    def test_non_integer_rc_raises_query_error(self, credentials: FinanzOnlineCredentials, uid_request: UidCheckRequest) -> None:
        """A non-integer rc takes the unexpected-error path, not retryable."""
        client, _ = _client_answering(_uid_reply(rc="abc", msg="x"))

        with pytest.raises(QueryError) as exc_info:
            client.query("SESSION123", credentials, uid_request)

        assert str(exc_info.value).startswith("Unexpected error: Malformed uidAbfrage response: rc: ")
        assert isinstance(exc_info.value.__cause__, MalformedSoapResponseError)
        assert exc_info.value.retryable is False
        assert exc_info.value.diagnostics is not None
        assert exc_info.value.diagnostics.operation == SoapOperation.UID_QUERY
        assert exc_info.value.diagnostics.return_code == ""

    def test_non_string_msg_raises_query_error(self, credentials: FinanzOnlineCredentials, uid_request: UidCheckRequest) -> None:
        """A msg that is not a string is refused, never converted with str()."""
        client, _ = _client_answering(SimpleNamespace(rc=0, msg=123, name=None))

        with pytest.raises(QueryError) as exc_info:
            client.query("SESSION123", credentials, uid_request)

        assert str(exc_info.value).startswith("Unexpected error: Malformed uidAbfrage response: msg: ")
        assert isinstance(exc_info.value.__cause__, MalformedSoapResponseError)

    def test_history_entry_without_envelope_keeps_the_original_error(self, credentials: FinanzOnlineCredentials, uid_request: UidCheckRequest) -> None:
        """A history entry lacking the envelope key does not replace the error being reported."""
        client, _ = _client_answering(_uid_reply(rc="abc"))
        history = MagicMock()
        history.last_received = {"http_headers": {}}
        history.last_sent = {"http_headers": {}}
        client._history = history

        with pytest.raises(QueryError) as exc_info:
            client.query("SESSION123", credentials, uid_request)

        assert str(exc_info.value).startswith("Unexpected error: Malformed uidAbfrage response: rc: ")
        assert exc_info.value.diagnostics is not None
        assert "No SOAP envelope captured" in exc_info.value.diagnostics.raw_response


class TestQueryLogging:
    """Query logs keep credentials and the session id masked."""

    def test_debug_log_masks_credentials_and_session_id(
        self,
        credentials: FinanzOnlineCredentials,
        uid_request: UidCheckRequest,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """tid, benid, pin and the session id never reach the log in clear text."""
        client, _ = _client_answering(_uid_reply(rc=1, msg="invalid"))

        with caplog.at_level(logging.DEBUG, logger="finanzonline_uid.adapters.finanzonline.uid_query_client"):
            client.query("SESSION123456", credentials, uid_request)

        text = caplog.text
        for secret in (credentials.tid, credentials.benid, credentials.pin, "SESSION123456"):
            assert secret not in text
        assert "SESS...3456" in text

    def test_soap_fault_message_is_the_fault_text(self, credentials: FinanzOnlineCredentials, uid_request: UidCheckRequest) -> None:
        """The QueryError reads 'SOAP fault: <fault message>'."""
        client, zeep = _client_answering(None)
        zeep.service.uidAbfrage.side_effect = Fault("Server busy")

        with pytest.raises(QueryError) as exc_info:
            client.query("SESSION123", credentials, uid_request)

        assert str(exc_info.value) == "SOAP fault: Server busy"
