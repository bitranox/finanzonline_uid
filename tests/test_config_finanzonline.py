"""FinanzOnline configuration loading: every scenario a single verse.

Tests cover load_finanzonline_config function with various config scenarios.
Uses MockConfig from conftest.py for testing without filesystem access.
"""

from __future__ import annotations

from typing import Any

import pytest

from finanzonline_uid.config import FinanzOnlineConfig, load_finanzonline_config
from finanzonline_uid.domain.errors import ConfigurationError
from finanzonline_uid.enums import EmailFormat

from conftest import MockConfig


# ============================================================================
# Successful Loading
# ============================================================================


@pytest.mark.os_agnostic
class TestSuccessfulLoading:
    """Configuration loads correctly with valid inputs."""

    def test_valid_config_is_loaded(self, finanzonline_config_dict: dict[str, Any]) -> None:
        """All fields from valid config are extracted correctly."""
        config = MockConfig(finanzonline_config_dict)

        result = load_finanzonline_config(config)

        assert isinstance(result, FinanzOnlineConfig)
        assert result.credentials.tid == "123456789"
        assert result.credentials.benid == "TESTUSER"
        assert result.credentials.pin == "secretpin"
        assert result.uid_tn == "ATU12345678"
        assert result.session_timeout == 45.0
        assert result.query_timeout == 60.0
        assert result.default_recipients == ["test@example.com", "admin@example.com"]

    def test_minimal_config_uses_defaults(
        self,
        minimal_finanzonline_config_dict: dict[str, Any],
    ) -> None:
        """Minimal config inherits default timeout values."""
        config = MockConfig(minimal_finanzonline_config_dict)

        result = load_finanzonline_config(config)

        assert result.credentials.tid == "123456789"
        assert result.session_timeout == 30.0
        assert result.query_timeout == 30.0
        assert result.default_recipients is None


# ============================================================================
# Missing Required Fields
# ============================================================================


@pytest.mark.os_agnostic
class TestMissingRequiredFields:
    """Missing required fields are reported with clear messages."""

    def test_missing_tid_raises_error(self) -> None:
        """Missing tid is reported in error message."""
        config = MockConfig(
            {
                "finanzonline": {
                    "benid": "TESTUSER",
                    "pin": "secretpin",
                    "uid_tn": "ATU12345678",
                    "herstellerid": "ATU12345678",
                }
            }
        )

        with pytest.raises(ConfigurationError) as exc_info:
            load_finanzonline_config(config)

        assert "finanzonline.tid" in str(exc_info.value)

    def test_missing_benid_raises_error(self) -> None:
        """Missing benid is reported in error message."""
        config = MockConfig(
            {
                "finanzonline": {
                    "tid": "123456789",
                    "pin": "secretpin",
                    "uid_tn": "ATU12345678",
                    "herstellerid": "ATU12345678",
                }
            }
        )

        with pytest.raises(ConfigurationError) as exc_info:
            load_finanzonline_config(config)

        assert "finanzonline.benid" in str(exc_info.value)

    def test_missing_pin_raises_error(self) -> None:
        """Missing pin is reported in error message."""
        config = MockConfig(
            {
                "finanzonline": {
                    "tid": "123456789",
                    "benid": "TESTUSER",
                    "uid_tn": "ATU12345678",
                    "herstellerid": "ATU12345678",
                }
            }
        )

        with pytest.raises(ConfigurationError) as exc_info:
            load_finanzonline_config(config)

        assert "finanzonline.pin" in str(exc_info.value)

    def test_missing_uid_tn_raises_error(self) -> None:
        """Missing uid_tn is reported in error message."""
        config = MockConfig(
            {
                "finanzonline": {
                    "tid": "123456789",
                    "benid": "TESTUSER",
                    "pin": "secretpin",
                    "herstellerid": "ATU12345678",
                }
            }
        )

        with pytest.raises(ConfigurationError) as exc_info:
            load_finanzonline_config(config)

        assert "finanzonline.uid_tn" in str(exc_info.value)

    def test_missing_herstellerid_raises_error(self) -> None:
        """Missing herstellerid is reported in error message."""
        config = MockConfig(
            {
                "finanzonline": {
                    "tid": "123456789",
                    "benid": "TESTUSER",
                    "pin": "secretpin",
                    "uid_tn": "ATU12345678",
                }
            }
        )

        with pytest.raises(ConfigurationError) as exc_info:
            load_finanzonline_config(config)

        assert "finanzonline.herstellerid" in str(exc_info.value)

    def test_all_missing_fields_are_reported(self) -> None:
        """All missing required fields appear in error message."""
        config = MockConfig({"finanzonline": {}})

        with pytest.raises(ConfigurationError) as exc_info:
            load_finanzonline_config(config)

        error_msg = str(exc_info.value)
        assert "tid" in error_msg
        assert "benid" in error_msg
        assert "pin" in error_msg
        assert "uid_tn" in error_msg
        assert "herstellerid" in error_msg


# ============================================================================
# UID Format Validation
# ============================================================================


@pytest.mark.os_agnostic
class TestUidFormatValidation:
    """UID format is validated correctly."""

    def test_non_atu_prefix_raises_error(self) -> None:
        """uid_tn not starting with ATU is rejected."""
        config = MockConfig(
            {
                "finanzonline": {
                    "tid": "123456789",
                    "benid": "TESTUSER",
                    "pin": "secretpin",
                    "uid_tn": "DE123456789",
                    "herstellerid": "ATU12345678",
                }
            }
        )

        with pytest.raises(ConfigurationError) as exc_info:
            load_finanzonline_config(config)

        assert "must start with 'ATU'" in str(exc_info.value)

    def test_lowercase_atu_is_accepted(self) -> None:
        """Lowercase atu prefix is accepted."""
        config = MockConfig(
            {
                "finanzonline": {
                    "tid": "123456789",
                    "benid": "TESTUSER",
                    "pin": "secretpin",
                    "uid_tn": "atu12345678",
                    "herstellerid": "ATU12345678",
                }
            }
        )

        result = load_finanzonline_config(config)

        assert result.uid_tn == "atu12345678"


# ============================================================================
# Edge Cases
# ============================================================================


@pytest.mark.os_agnostic
class TestEdgeCases:
    """Edge cases are handled gracefully."""

    def test_empty_section_raises_error(self) -> None:
        """Empty finanzonline section raises error."""
        config = MockConfig({})

        with pytest.raises(ConfigurationError) as exc_info:
            load_finanzonline_config(config)

        assert "Missing required" in str(exc_info.value)

    def test_non_dict_section_raises_error(self) -> None:
        """Non-dict finanzonline section raises error."""
        config = MockConfig({"finanzonline": "invalid"})

        with pytest.raises(ConfigurationError):
            load_finanzonline_config(config)

    def test_invalid_timeout_uses_default(self) -> None:
        """Invalid timeout string falls back to default."""
        config = MockConfig(
            {
                "finanzonline": {
                    "tid": "123456789",
                    "benid": "TESTUSER",
                    "pin": "secretpin",
                    "uid_tn": "ATU12345678",
                    "herstellerid": "ATU12345678",
                    "session_timeout": "invalid",
                    "query_timeout": "invalid",
                }
            }
        )

        result = load_finanzonline_config(config)

        assert result.session_timeout == 30.0
        assert result.query_timeout == 30.0

    def test_integer_timeout_is_converted(self) -> None:
        """Integer timeout values are converted to float."""
        config = MockConfig(
            {
                "finanzonline": {
                    "tid": "123456789",
                    "benid": "TESTUSER",
                    "pin": "secretpin",
                    "uid_tn": "ATU12345678",
                    "herstellerid": "ATU12345678",
                    "session_timeout": 45,
                    "query_timeout": 60,
                }
            }
        )

        result = load_finanzonline_config(config)

        assert result.session_timeout == 45.0
        assert result.query_timeout == 60.0


# ============================================================================
# Recipients Handling
# ============================================================================


@pytest.mark.os_agnostic
class TestRecipientsHandling:
    """Recipients list is handled correctly."""

    def test_empty_recipients_becomes_none(self) -> None:
        """Empty recipients list becomes None."""
        config = MockConfig(
            {
                "finanzonline": {
                    "tid": "123456789",
                    "benid": "TESTUSER",
                    "pin": "secretpin",
                    "uid_tn": "ATU12345678",
                    "herstellerid": "ATU12345678",
                    "default_recipients": [],
                }
            }
        )

        result = load_finanzonline_config(config)

        assert result.default_recipients is None

    def test_non_list_recipients_becomes_none(self) -> None:
        """Non-list recipients value becomes None."""
        config = MockConfig(
            {
                "finanzonline": {
                    "tid": "123456789",
                    "benid": "TESTUSER",
                    "pin": "secretpin",
                    "uid_tn": "ATU12345678",
                    "herstellerid": "ATU12345678",
                    "default_recipients": "not-a-list",
                }
            }
        )

        result = load_finanzonline_config(config)

        assert result.default_recipients is None

    def test_recipients_are_converted_to_strings(self) -> None:
        """Non-string recipients are converted to strings."""
        config = MockConfig(
            {
                "finanzonline": {
                    "tid": "123456789",
                    "benid": "TESTUSER",
                    "pin": "secretpin",
                    "uid_tn": "ATU12345678",
                    "herstellerid": "ATU12345678",
                    "default_recipients": [123, "email@test.com"],
                }
            }
        )

        result = load_finanzonline_config(config)

        assert result.default_recipients == ["123", "email@test.com"]


# ============================================================================
# Type Conversion
# ============================================================================


@pytest.mark.os_agnostic
class TestTypeConversion:
    """Credential values are converted to strings correctly."""

    def test_integer_tid_is_converted(self) -> None:
        """Integer tid is converted to string."""
        config = MockConfig(
            {
                "finanzonline": {
                    "tid": 123456789,
                    "benid": "TESTUSER",
                    "pin": "secretpin",
                    "uid_tn": "ATU12345678",
                    "herstellerid": "ATU12345678",
                }
            }
        )

        result = load_finanzonline_config(config)

        assert result.credentials.tid == "123456789"


# ============================================================================
# Dataclass Properties
# ============================================================================


@pytest.mark.os_agnostic
class TestFinanzOnlineConfigProperties:
    """FinanzOnlineConfig dataclass has expected properties."""

    def test_is_immutable(self, finanzonline_config_dict: dict[str, Any]) -> None:
        """FinanzOnlineConfig is frozen and cannot be modified."""
        config = MockConfig(finanzonline_config_dict)
        result = load_finanzonline_config(config)

        with pytest.raises(AttributeError):
            result.uid_tn = "ATU99999999"  # type: ignore[misc]

    def test_uses_slots(self) -> None:
        """FinanzOnlineConfig uses slots for memory efficiency."""
        assert hasattr(FinanzOnlineConfig, "__slots__")


# ============================================================================
# Email Format Parsing
# ============================================================================


@pytest.mark.os_agnostic
class TestEmailFormatParsing:
    """Email format configuration is parsed correctly."""

    def test_default_email_format_is_both(self, minimal_finanzonline_config_dict: dict[str, Any]) -> None:
        """Default email format is BOTH when not specified."""
        config = MockConfig(minimal_finanzonline_config_dict)

        result = load_finanzonline_config(config)

        assert result.email_format == EmailFormat.BOTH

    def test_html_format_is_parsed(self, minimal_finanzonline_config_dict: dict[str, Any]) -> None:
        """HTML email format is parsed correctly."""
        minimal_finanzonline_config_dict["finanzonline"]["email_format"] = "html"
        config = MockConfig(minimal_finanzonline_config_dict)

        result = load_finanzonline_config(config)

        assert result.email_format == EmailFormat.HTML

    def test_plain_format_is_parsed(self, minimal_finanzonline_config_dict: dict[str, Any]) -> None:
        """PLAIN email format is parsed correctly."""
        minimal_finanzonline_config_dict["finanzonline"]["email_format"] = "plain"
        config = MockConfig(minimal_finanzonline_config_dict)

        result = load_finanzonline_config(config)

        assert result.email_format == EmailFormat.PLAIN

    def test_both_format_is_parsed(self, minimal_finanzonline_config_dict: dict[str, Any]) -> None:
        """BOTH email format is parsed correctly."""
        minimal_finanzonline_config_dict["finanzonline"]["email_format"] = "both"
        config = MockConfig(minimal_finanzonline_config_dict)

        result = load_finanzonline_config(config)

        assert result.email_format == EmailFormat.BOTH

    def test_uppercase_format_is_normalized(self, minimal_finanzonline_config_dict: dict[str, Any]) -> None:
        """Uppercase email format strings are normalized."""
        minimal_finanzonline_config_dict["finanzonline"]["email_format"] = "HTML"
        config = MockConfig(minimal_finanzonline_config_dict)

        result = load_finanzonline_config(config)

        assert result.email_format == EmailFormat.HTML

    def test_invalid_format_uses_default(self, minimal_finanzonline_config_dict: dict[str, Any]) -> None:
        """Invalid email format falls back to BOTH."""
        minimal_finanzonline_config_dict["finanzonline"]["email_format"] = "invalid"
        config = MockConfig(minimal_finanzonline_config_dict)

        result = load_finanzonline_config(config)

        assert result.email_format == EmailFormat.BOTH

    def test_non_string_format_uses_default(self, minimal_finanzonline_config_dict: dict[str, Any]) -> None:
        """Non-string email format falls back to BOTH."""
        minimal_finanzonline_config_dict["finanzonline"]["email_format"] = 123
        config = MockConfig(minimal_finanzonline_config_dict)

        result = load_finanzonline_config(config)

        assert result.email_format == EmailFormat.BOTH
