"""Tests for application use cases.

Tests cover CheckUidUseCase with mocked ports to verify
orchestration logic without real external dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from uid_check_austria.application.use_cases import CheckUidUseCase
from uid_check_austria.domain.errors import QueryError, SessionError
from uid_check_austria.domain.models import (
    Address,
    FinanzOnlineCredentials,
    SessionInfo,
    UidCheckRequest,
    UidCheckResult,
)


@pytest.fixture
def credentials() -> FinanzOnlineCredentials:
    """Valid credentials fixture with XSD-compliant values."""
    return FinanzOnlineCredentials(
        tid="123456789",
        benid="TESTUSER",
        pin="secretpin",
        herstellerid="ATU12345678",
    )


@pytest.fixture
def mock_session_client() -> MagicMock:
    """Mock session client fixture."""
    client = MagicMock()
    client.login.return_value = SessionInfo(
        session_id="TEST_SESSION_123",
        return_code=0,
        message="Login successful",
    )
    client.logout.return_value = True
    return client


@pytest.fixture
def mock_query_client() -> MagicMock:
    """Mock query client fixture."""
    client = MagicMock()
    client.query.return_value = UidCheckResult(
        uid="DE123456789",
        return_code=0,
        message="UID is valid",
        name="Test Company GmbH",
        address=Address(line1="Test Company GmbH", line2="Street 1", line3="12345 City"),
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    return client


class TestCheckUidUseCase:
    """Tests for CheckUidUseCase."""

    def test_execute_success(
        self,
        credentials: FinanzOnlineCredentials,
        mock_session_client: MagicMock,
        mock_query_client: MagicMock,
    ) -> None:
        """Should execute full flow and return valid result."""
        use_case = CheckUidUseCase(mock_session_client, mock_query_client)

        result = use_case.execute(credentials, "ATU12345678", "DE123456789")

        assert result.is_valid
        assert result.uid == "DE123456789"
        assert result.name == "Test Company GmbH"
        mock_session_client.login.assert_called_once_with(credentials)
        mock_session_client.logout.assert_called_once()

    def test_execute_calls_query_with_correct_params(
        self,
        credentials: FinanzOnlineCredentials,
        mock_session_client: MagicMock,
        mock_query_client: MagicMock,
    ) -> None:
        """Should call query with session and request params."""
        use_case = CheckUidUseCase(mock_session_client, mock_query_client)

        use_case.execute(credentials, "ATU12345678", "DE123456789")

        mock_query_client.query.assert_called_once()
        call_args = mock_query_client.query.call_args
        assert call_args.kwargs["session_id"] == "TEST_SESSION_123"
        assert call_args.kwargs["credentials"] == credentials
        request = call_args.kwargs["request"]
        assert isinstance(request, UidCheckRequest)
        assert request.uid_tn == "ATU12345678"
        assert request.uid == "DE123456789"
        assert request.stufe == 2

    def test_execute_logout_always_called(
        self,
        credentials: FinanzOnlineCredentials,
        mock_session_client: MagicMock,
        mock_query_client: MagicMock,
    ) -> None:
        """Should always attempt logout even if query fails."""
        mock_query_client.query.side_effect = QueryError("Query failed")
        use_case = CheckUidUseCase(mock_session_client, mock_query_client)

        with pytest.raises(QueryError):
            use_case.execute(credentials, "ATU12345678", "DE123456789")

        mock_session_client.logout.assert_called_once()

    def test_execute_login_failure(
        self,
        credentials: FinanzOnlineCredentials,
        mock_session_client: MagicMock,
        mock_query_client: MagicMock,
    ) -> None:
        """Should raise SessionError if login fails."""
        mock_session_client.login.return_value = SessionInfo(
            session_id="",
            return_code=-4,
            message="Not authorized",
        )
        use_case = CheckUidUseCase(mock_session_client, mock_query_client)

        with pytest.raises(SessionError, match="Login failed"):
            use_case.execute(credentials, "ATU12345678", "DE123456789")

        mock_query_client.query.assert_not_called()

    def test_execute_logout_failure_non_fatal(
        self,
        credentials: FinanzOnlineCredentials,
        mock_session_client: MagicMock,
        mock_query_client: MagicMock,
    ) -> None:
        """Should not fail operation if logout fails."""
        mock_session_client.logout.side_effect = Exception("Logout error")
        use_case = CheckUidUseCase(mock_session_client, mock_query_client)

        # Should not raise despite logout failure
        result = use_case.execute(credentials, "ATU12345678", "DE123456789")

        assert result.is_valid

    def test_execute_invalid_uid_result(
        self,
        credentials: FinanzOnlineCredentials,
        mock_session_client: MagicMock,
        mock_query_client: MagicMock,
    ) -> None:
        """Should return invalid result for invalid UID."""
        mock_query_client.query.return_value = UidCheckResult(
            uid="DE123456789",
            return_code=1,
            message="UID is invalid",
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        use_case = CheckUidUseCase(mock_session_client, mock_query_client)

        result = use_case.execute(credentials, "ATU12345678", "DE123456789")

        assert result.is_invalid
        assert result.return_code == 1

    def test_execute_invalid_uid_tn_raises(
        self,
        credentials: FinanzOnlineCredentials,
        mock_session_client: MagicMock,
        mock_query_client: MagicMock,
    ) -> None:
        """Should raise ValueError for invalid uid_tn."""
        use_case = CheckUidUseCase(mock_session_client, mock_query_client)

        with pytest.raises(ValueError, match="ATU"):
            use_case.execute(credentials, "DE12345678", "FR123456789")

        # Login should not be called for invalid request
        mock_session_client.login.assert_not_called()
