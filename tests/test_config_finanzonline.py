"""FinanzOnline configuration loading: every scenario a single verse.

Tests cover load_finanzonline_config function with various config scenarios.
Uses MockConfig from conftest.py for testing without filesystem access.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from conftest import MockConfig
from finanzonline_uid.config import FinanzOnlineConfig, load_app_config, load_finanzonline_config
from finanzonline_uid.domain.errors import ConfigurationError
from finanzonline_uid.enums import EmailFormat, FileFormat, Language

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

    def test_default_email_format_is_html(self, minimal_finanzonline_config_dict: dict[str, Any]) -> None:
        """Default email format is HTML when not specified."""
        config = MockConfig(minimal_finanzonline_config_dict)

        result = load_finanzonline_config(config)

        assert result.email_format == EmailFormat.HTML

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
        """Invalid email format falls back to HTML."""
        minimal_finanzonline_config_dict["finanzonline"]["email_format"] = "invalid"
        config = MockConfig(minimal_finanzonline_config_dict)

        result = load_finanzonline_config(config)

        assert result.email_format == EmailFormat.HTML

    def test_non_string_format_uses_default(self, minimal_finanzonline_config_dict: dict[str, Any]) -> None:
        """Non-string email format falls back to HTML."""
        minimal_finanzonline_config_dict["finanzonline"]["email_format"] = 123
        config = MockConfig(minimal_finanzonline_config_dict)

        result = load_finanzonline_config(config)

        assert result.email_format == EmailFormat.HTML


# ============================================================================
# Refusal order and exact text
# ============================================================================


def _fo(**settings: object) -> MockConfig:
    """A configuration whose finanzonline section is the valid minimum plus `settings`."""
    section: dict[str, object] = {
        "tid": "123456789",
        "benid": "TESTUSER",
        "pin": "secretpin",
        "uid_tn": "ATU12345678",
        "herstellerid": "ATU12345678",
    }
    section.update(settings)
    return MockConfig({"finanzonline": section})


@pytest.mark.os_agnostic
class TestRefusals:
    """Each refusal keeps its exception type, its text and its precedence."""

    def test_missing_message_lists_fields_in_order(self) -> None:
        with pytest.raises(ConfigurationError) as exc_info:
            load_finanzonline_config(MockConfig({"finanzonline": {"pin": "secretpin"}}))

        assert str(exc_info.value) == (
            "Missing required FinanzOnline configuration: finanzonline.tid, finanzonline.benid, finanzonline.uid_tn, "
            "finanzonline.herstellerid. Configure via config file or environment variables."
        )

    def test_missing_fields_win_over_a_wrong_uid_prefix(self) -> None:
        with pytest.raises(ConfigurationError, match="^Missing required"):
            load_finanzonline_config(_fo(tid="", uid_tn="DE123456789"))

    def test_invalid_credentials_win_over_a_wrong_uid_prefix(self) -> None:
        with pytest.raises(ConfigurationError, match="^Invalid credentials: "):
            load_finanzonline_config(_fo(tid="1", uid_tn="DE123456789"))

    def test_wrong_uid_prefix_text(self) -> None:
        with pytest.raises(ConfigurationError) as exc_info:
            load_finanzonline_config(_fo(uid_tn="DE123456789"))

        assert str(exc_info.value) == "finanzonline.uid_tn must start with 'ATU', got: DE123456789"

    def test_false_credential_counts_as_missing(self) -> None:
        with pytest.raises(ConfigurationError, match=r"finanzonline\.pin"):
            load_finanzonline_config(_fo(pin=False))


# ============================================================================
# Output file format
# ============================================================================


@pytest.mark.os_agnostic
class TestOutputFormat:
    """output_format becomes a FileFormat; anything unknown falls back to HTML."""

    def test_default_is_html(self) -> None:
        assert load_finanzonline_config(_fo()).output_format is FileFormat.HTML

    @pytest.mark.parametrize(("raw", "expected"), [("json", FileFormat.JSON), ("TXT", FileFormat.TXT), ("Html", FileFormat.HTML)])
    def test_known_value_is_parsed_case_insensitively(self, raw: str, expected: FileFormat) -> None:
        assert load_finanzonline_config(_fo(output_format=raw)).output_format is expected

    @pytest.mark.parametrize("raw", ["pdf", " json", 7, ""])
    def test_unknown_value_falls_back_to_html(self, raw: object) -> None:
        assert load_finanzonline_config(_fo(output_format=raw)).output_format is FileFormat.HTML


# ============================================================================
# Numbers and paths
# ============================================================================


@pytest.mark.os_agnostic
class TestNumbersAndPaths:
    """Numeric settings coerce or fall back; path settings normalise or fall back."""

    def test_rate_limit_settings(self) -> None:
        result = load_finanzonline_config(_fo(ratelimit_queries=12.9, ratelimit_hours=6, cache_results_hours="x"))

        assert (result.ratelimit_queries, result.ratelimit_hours, result.cache_results_hours) == (12, 6.0, 48.0)

    def test_rate_limit_defaults(self) -> None:
        result = load_finanzonline_config(_fo(ratelimit_queries="many"))

        assert (result.ratelimit_queries, result.ratelimit_hours) == (50, 24.0)

    def test_configured_state_files_are_used(self, tmp_path: Path) -> None:
        result = load_finanzonline_config(_fo(cache_file=str(tmp_path / "c.json"), ratelimit_file=str(tmp_path / "r.json")))

        assert (result.cache_file, result.ratelimit_file) == (tmp_path / "c.json", tmp_path / "r.json")

    @pytest.mark.parametrize("raw", ["", "   ", None, True])
    def test_blank_or_mistyped_state_file_uses_the_platform_default(self, raw: object) -> None:
        result = load_finanzonline_config(_fo(cache_file=raw, ratelimit_file=raw))

        assert result.cache_file is not None and result.cache_file.name == "uid_cache.json"
        assert result.ratelimit_file is not None and result.ratelimit_file.name == "rate_limits.json"

    def test_output_dir_is_none_when_unset(self) -> None:
        assert load_finanzonline_config(_fo(output_dir="")).output_dir is None

    def test_output_dir_is_none_when_absent(self) -> None:
        assert load_finanzonline_config(_fo()).output_dir is None

    def test_output_dir_expands_the_home_directory(self) -> None:
        result = load_finanzonline_config(_fo(output_dir="~/uid-results"))

        assert result.output_dir == Path.home() / "uid-results"

    @pytest.mark.parametrize("raw", [False, 0, 0.0, [], {}])
    def test_an_empty_or_false_output_dir_turns_result_files_off(self, raw: object) -> None:
        # The release read every falsy value as "off"; 0 must not become a directory named "0".
        assert load_finanzonline_config(_fo(output_dir=raw)).output_dir is None

    @pytest.mark.parametrize("raw", ["   ", "\t", " \t\n "])
    def test_a_whitespace_only_output_dir_turns_result_files_off(self, raw: str) -> None:
        # Stripped, it would be Path("."), and result files would land in the current directory.
        assert load_finanzonline_config(_fo(output_dir=raw)).output_dir is None

    def test_surrounding_whitespace_is_stripped_from_every_path_setting(self, tmp_path: Path) -> None:
        # One rule for all three: a stray space around a path in a config file is not part of the name.
        result = load_finanzonline_config(
            _fo(
                output_dir=f"  {tmp_path / 'out'}\t",
                cache_file=f" {tmp_path / 'c.json'} ",
                ratelimit_file=f"\t{tmp_path / 'r.json'}  ",
            )
        )

        assert (result.output_dir, result.cache_file, result.ratelimit_file) == (tmp_path / "out", tmp_path / "c.json", tmp_path / "r.json")

    def test_a_digit_only_output_dir_keeps_its_digits(self) -> None:
        assert load_finanzonline_config(_fo(output_dir=4711)).output_dir == Path("4711")

    @pytest.mark.parametrize(
        ("raw", "type_name"),
        [(True, "bool"), (["x"], "list"), (1.5, "float"), ({"a": 1}, "dict")],
    )
    def test_mistyped_output_dir_is_refused_as_a_configuration_error(self, raw: object, type_name: str) -> None:
        # The release crashed with AttributeError on these; falling back to None would
        # switch result files off without a word.
        expected = f"Invalid FinanzOnline configuration: finanzonline.output_dir: must be a directory path given as text, got {type_name}"

        with pytest.raises(ConfigurationError) as excinfo:
            load_finanzonline_config(_fo(output_dir=raw))

        assert excinfo.value.message == expected
        assert "pydantic" not in excinfo.value.message

    def test_json_text_recipients_from_dotenv_are_parsed(self) -> None:
        result = load_finanzonline_config(_fo(default_recipients='["a@test.com", "b@test.com"]'))

        assert result.default_recipients == ["a@test.com", "b@test.com"]


# ============================================================================
# Application settings: language
# ============================================================================


@pytest.mark.os_agnostic
class TestAppConfigLanguage:
    """The [app] language is normalised at the boundary; an unsupported one falls back silently."""

    def test_missing_section_uses_english(self) -> None:
        assert load_app_config(MockConfig({})).language is Language.EN

    def test_non_table_section_uses_english(self) -> None:
        assert load_app_config(MockConfig({"app": "de"})).language is Language.EN

    @pytest.mark.parametrize(("raw", "expected"), [("de", Language.DE), (" FR ", Language.FR), ("ru", Language.RU), ("", Language.EN)])
    def test_supported_language_is_normalised(self, raw: str, expected: Language) -> None:
        assert load_app_config(MockConfig({"app": {"language": raw}})).language is expected

    def test_unsupported_language_falls_back_without_a_log_record(self, caplog: pytest.LogCaptureFixture) -> None:
        # The CLI reads [app] before logging is initialised; any record emitted here would reach
        # stderr unformatted through logging.lastResort.
        with caplog.at_level(logging.DEBUG):
            result = load_app_config(MockConfig({"app": {"language": "xx"}}))

        assert result.language is Language.EN
        assert caplog.records == []
