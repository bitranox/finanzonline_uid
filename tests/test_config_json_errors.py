"""``config --format json`` reports its own failures as one JSON error record on stdout.

The record reuses the field names of the ``check`` error record that apply to a command which
checks no UID. The stderr line and the exit code are the same as with ``--format human``, which
leaves stdout empty. The configuration comes in through Click's ``obj``.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from typing import Any

import pytest
from click.testing import CliRunner, Result
from lib_layered_config import Config
from log_lines import LOG_LINE

from finanzonline_uid import cli as cli_mod
from finanzonline_uid.adapters.output import format_error_json
from finanzonline_uid.domain.errors import CheckErrorInfo, ErrorKind
from finanzonline_uid.domain.return_codes import CliExitCode

_CONFIG_DATA: dict[str, Any] = {"email": {"smtp_hosts": ["smtp.example.com"]}, "empty": {}}


def _config(args: list[str]) -> Result:
    """Run ``config <args>`` against a fixed configuration."""

    def load_config(*, profile: str | None = None) -> Config:
        return Config(_CONFIG_DATA, {})

    deps = dataclasses.replace(cli_mod.production_dependencies(), load_config=load_config)
    return CliRunner().invoke(cli_mod.cli, ["config", *args], obj=deps)


def _stderr(result: Result) -> str:
    return LOG_LINE.sub("", result.stderr)


@pytest.mark.os_agnostic
@pytest.mark.parametrize("section", ["nonexistent", "empty"])
def test_json_missing_section_is_one_error_record_on_stdout(section: str) -> None:
    result = _config(["--format", "json", "--section", section])

    assert result.exit_code == 1
    assert _stderr(result) == f"Section '{section}' not found or empty\n"
    record: dict[str, Any] = json.loads(result.stdout)
    assert list(record) == ["error", "error_type", "message", "timestamp"]
    assert (record["error"], record["error_type"], record["message"]) == (True, "Validation Error", f"Section '{section}' not found or empty")
    assert datetime.fromisoformat(record["timestamp"]).tzinfo is not None


@pytest.mark.os_agnostic
def test_config_error_record_fields_are_named_and_typed_as_in_the_check_error_record() -> None:
    """Every key of the config record is a key of the check record, with a value of the same type."""
    config_record: dict[str, Any] = json.loads(_config(["--format", "json", "--section", "nonexistent"]).stdout)
    info = CheckErrorInfo(error_type=ErrorKind.VALIDATION, message="m", exit_code=CliExitCode.CONFIG_ERROR)
    check_record: dict[str, Any] = json.loads(format_error_json(info, "DE123456789"))

    assert set(config_record) <= set(check_record)
    assert {key: type(value) for key, value in config_record.items()} == {key: type(check_record[key]) for key in config_record}


@pytest.mark.os_agnostic
def test_human_missing_section_leaves_stdout_empty_with_the_same_stderr_and_exit_code() -> None:
    human = _config(["--section", "nonexistent"])
    machine = _config(["--format", "json", "--section", "nonexistent"])

    assert (human.stdout, human.exit_code, _stderr(human)) == ("", machine.exit_code, _stderr(machine))


@pytest.mark.os_agnostic
def test_json_existing_section_is_unchanged() -> None:
    result = _config(["--format", "json", "--section", "email"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"email": {"smtp_hosts": ["smtp.example.com"]}}
