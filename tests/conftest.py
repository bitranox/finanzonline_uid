"""Shared pytest fixtures for the entire test suite.

Centralizes test infrastructure following clean architecture principles:
- All shared fixtures live here
- Tests import fixtures implicitly via pytest's conftest discovery
- Fixtures use descriptive names that read as plain English

OS-Specific Markers:
    os_agnostic: Tests that run identically on all platforms
    posix_only: Tests requiring POSIX-compliant systems (Linux, macOS)
    windows_only: Tests requiring Windows
    macos_only: Tests requiring macOS

Coverage Configuration:
    When using coverage, always use JSON output to avoid SQL locks.
    Use `coverage json` instead of `coverage report` during parallel execution.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable, Iterator
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner
from lib_layered_config import Config

import lib_cli_exit_tools


# ============================================================================
# pytest configuration
# ============================================================================


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for OS-specific tests."""
    config.addinivalue_line("markers", "os_agnostic: tests that run on all platforms")
    config.addinivalue_line("markers", "posix_only: tests requiring POSIX systems (Linux, macOS)")
    config.addinivalue_line("markers", "windows_only: tests requiring Windows")
    config.addinivalue_line("markers", "macos_only: tests requiring macOS")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip tests based on current platform."""
    is_windows = sys.platform == "win32"
    is_macos = sys.platform == "darwin"
    is_posix = sys.platform != "win32"

    skip_windows = pytest.mark.skip(reason="Windows-only test")
    skip_posix = pytest.mark.skip(reason="POSIX-only test")
    skip_macos = pytest.mark.skip(reason="macOS-only test")

    for item in items:
        if "windows_only" in item.keywords and not is_windows:
            item.add_marker(skip_windows)
        if "posix_only" in item.keywords and not is_posix:
            item.add_marker(skip_posix)
        if "macos_only" in item.keywords and not is_macos:
            item.add_marker(skip_macos)


# ============================================================================
# Internationalization setup
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def ensure_english_locale() -> None:
    """Set English locale at session start for consistent test output.

    Many tests expect English strings (e.g., 'VALID', 'Timestamp:').
    This ensures the i18n system starts in English before any tests run.
    """
    from finanzonline_uid.i18n import setup_locale

    setup_locale("en")


# ============================================================================
# Environment setup
# ============================================================================


def _load_dotenv() -> None:
    """Load .env file when it exists for integration test configuration."""
    try:
        from dotenv import load_dotenv

        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            load_dotenv(env_file)
    except ImportError:
        pass


_load_dotenv()


# ============================================================================
# ANSI and CLI configuration helpers
# ============================================================================


ANSI_ESCAPE_PATTERN = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
CONFIG_FIELDS: tuple[str, ...] = tuple(field.name for field in fields(type(lib_cli_exit_tools.config)))


def _remove_ansi_codes(text: str) -> str:
    """Strip ANSI escape sequences from text.

    Tests compare human-readable CLI output; stripping colour codes keeps
    assertions stable across environments.
    """
    return ANSI_ESCAPE_PATTERN.sub("", text)


def _snapshot_cli_config() -> dict[str, object]:
    """Capture every attribute from lib_cli_exit_tools.config."""
    return {name: getattr(lib_cli_exit_tools.config, name) for name in CONFIG_FIELDS}


def _restore_cli_config(snapshot: dict[str, object]) -> None:
    """Reapply the previously captured CLI configuration."""
    for name, value in snapshot.items():
        setattr(lib_cli_exit_tools.config, name, value)


# ============================================================================
# CLI fixtures
# ============================================================================


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a fresh CliRunner per test."""
    return CliRunner()


@pytest.fixture
def strip_ansi() -> Callable[[str], str]:
    """Return a helper that strips ANSI escape sequences from a string."""
    return _remove_ansi_codes


@pytest.fixture
def preserve_traceback_state() -> Iterator[None]:
    """Snapshot and restore the entire lib_cli_exit_tools configuration."""
    snapshot = _snapshot_cli_config()
    try:
        yield
    finally:
        _restore_cli_config(snapshot)


@pytest.fixture
def isolated_traceback_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset traceback flags to a known baseline before each test."""
    lib_cli_exit_tools.reset_config()
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback", False, raising=False)
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback_force_color", False, raising=False)


# ============================================================================
# Configuration fixtures
# ============================================================================


class MockConfig(Config):
    """Reusable mock configuration for testing CLI commands.

    Provides a minimal Config implementation that returns data from a dict
    without touching the filesystem.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        object.__setattr__(self, "_mock_data", data)

    def as_dict(self) -> dict[str, Any]:
        return dict(object.__getattribute__(self, "_mock_data"))

    def to_json(self, *, indent: int | None = None) -> str:
        import json

        return json.dumps(object.__getattribute__(self, "_mock_data"), indent=indent)

    def get(self, key: str, default: Any = None) -> Any:
        return object.__getattribute__(self, "_mock_data").get(key, default)


@pytest.fixture
def mock_config_factory() -> Callable[[dict[str, Any]], MockConfig]:
    """Provide a factory that creates MockConfig instances with given data."""
    return MockConfig


@pytest.fixture
def email_test_config() -> dict[str, Any]:
    """Provide standard email configuration for tests."""
    return {
        "email": {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "sender@test.com",
        }
    }


@pytest.fixture
def clear_config_cache() -> Iterator[None]:
    """Clear the get_config lru_cache before each test.

    Note: Only clears before, not after, to avoid errors when the function
    has been monkeypatched during the test (losing cache_clear method).
    """
    from finanzonline_uid import config as config_mod

    config_mod.get_config.cache_clear()
    yield


# ============================================================================
# Domain model fixtures
# ============================================================================


@pytest.fixture
def valid_credentials() -> Any:
    """Provide valid FinanzOnline credentials for tests."""
    from finanzonline_uid.domain.models import FinanzOnlineCredentials

    return FinanzOnlineCredentials(
        tid="123456789",
        benid="TESTUSER",
        pin="testpin123",
        herstellerid="ATU12345678",
    )


@pytest.fixture
def valid_uid_request() -> Any:
    """Provide a valid UID check request for tests."""
    from finanzonline_uid.domain.models import UidCheckRequest

    return UidCheckRequest(
        uid_tn="ATU12345678",
        uid="DE987654321",
        stufe=2,
    )


@pytest.fixture
def valid_session_info() -> Any:
    """Provide a valid session info for tests."""
    from finanzonline_uid.domain.models import SessionInfo

    return SessionInfo(
        session_id="TEST_SESSION_123",
        return_code=0,
        message="Login successful",
    )


@pytest.fixture
def valid_uid_result() -> Any:
    """Provide a valid UID check result for tests."""
    from finanzonline_uid.domain.models import Address, UidCheckResult

    return UidCheckResult(
        uid="DE123456789",
        return_code=0,
        message="UID is valid",
        name="Test Company GmbH",
        address=Address(
            line1="Test Company GmbH",
            line2="Test Street 123",
            line3="12345 Test City",
        ),
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def invalid_uid_result() -> Any:
    """Provide an invalid UID check result for tests."""
    from finanzonline_uid.domain.models import UidCheckResult

    return UidCheckResult(
        uid="XX123456789",
        return_code=1,
        message="UID is invalid",
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def valid_email_config() -> Any:
    """Provide a valid email configuration for tests."""
    from finanzonline_uid.mail import EmailConfig

    return EmailConfig(
        smtp_hosts=["smtp.test.com:587"],
        from_address="sender@test.com",
    )


# ============================================================================
# FinanzOnline configuration fixtures
# ============================================================================


@pytest.fixture
def finanzonline_config_dict() -> dict[str, Any]:
    """Provide a valid FinanzOnline configuration dictionary."""
    return {
        "finanzonline": {
            "tid": "123456789",
            "benid": "TESTUSER",
            "pin": "secretpin",
            "uid_tn": "ATU12345678",
            "herstellerid": "ATU12345678",
            "session_timeout": 45.0,
            "query_timeout": 60.0,
            "default_recipients": ["test@example.com", "admin@example.com"],
        }
    }


@pytest.fixture
def minimal_finanzonline_config_dict() -> dict[str, Any]:
    """Provide minimal required FinanzOnline configuration."""
    return {
        "finanzonline": {
            "tid": "123456789",
            "benid": "TESTUSER",
            "pin": "secretpin",
            "uid_tn": "ATU12345678",
            "herstellerid": "ATU12345678",
        }
    }


@pytest.fixture
def mock_fo_config(valid_credentials: Any) -> MagicMock:
    """Provide a mock FinanzOnline configuration object."""
    mock = MagicMock()
    mock.uid_tn = "ATU12345678"
    mock.credentials = valid_credentials
    mock.session_timeout = 30.0
    mock.query_timeout = 30.0
    mock.default_recipients = []
    mock.cache_results_hours = 0  # Disable cache in tests
    mock.cache_file = None
    return mock


# ============================================================================
# SOAP client fixtures
# ============================================================================


@pytest.fixture
def mock_soap_login_response() -> MagicMock:
    """Provide a mock successful SOAP login response."""
    response = MagicMock()
    response.rc = 0
    response.msg = "Login successful"
    response.id = "SESSION123456"
    return response


@pytest.fixture
def mock_soap_query_response() -> MagicMock:
    """Provide a mock successful SOAP query response."""
    response = MagicMock()
    response.rc = 0
    response.msg = "UID is valid"
    response.name = "Test Company GmbH"
    response.adr_1 = "Test Company GmbH"
    response.adr_2 = "Test Street 123"
    response.adr_3 = "12345 Test City"
    response.adr_4 = ""
    response.adr_5 = ""
    response.adr_6 = "DE"
    return response


# ============================================================================
# Email/SMTP fixtures
# ============================================================================


@pytest.fixture
def smtp_config_from_env() -> Any:
    """Load SMTP configuration from environment for integration tests.

    Returns None and marks skip if environment is not configured.
    """
    import os

    from finanzonline_uid.mail import EmailConfig

    smtp_server = os.getenv("TEST_SMTP_SERVER")
    email_address = os.getenv("TEST_EMAIL_ADDRESS")

    if not smtp_server or not email_address:
        pytest.skip("TEST_SMTP_SERVER or TEST_EMAIL_ADDRESS not configured in .env")

    return EmailConfig(
        smtp_hosts=[smtp_server],
        from_address=email_address,
        timeout=10.0,
    )


# ============================================================================
# Test data factories
# ============================================================================


@pytest.fixture
def make_uid_result() -> Callable[..., Any]:
    """Factory for creating UidCheckResult with custom parameters."""
    from finanzonline_uid.domain.models import Address, UidCheckResult

    def _factory(
        uid: str = "DE123456789",
        return_code: int = 0,
        message: str = "UID is valid",
        name: str = "Test Company GmbH",
        with_address: bool = True,
    ) -> UidCheckResult:
        address = (
            Address(
                line1="Test Company GmbH",
                line2="Street 1",
                line3="12345 City",
            )
            if with_address
            else None
        )
        return UidCheckResult(
            uid=uid,
            return_code=return_code,
            message=message,
            name=name if with_address else "",
            address=address,
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )

    return _factory
