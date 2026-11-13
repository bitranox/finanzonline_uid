"""``check --format json`` writes exactly one JSON document to stdout; progress text goes to stderr.

The "Result saved to" note of ``--outputdir``, the ``--interactive`` prompt and the retry
countdown are written to stderr in json mode, on success and on failure, so a caller can parse
the WHOLE stdout (no stripping) as one document. With ``--format human`` the same lines stay on
stdout, where they have always been. Collaborators come in through Click's ``obj``.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result
from lib_layered_config import Config

from finanzonline_uid import cli as cli_mod
from finanzonline_uid.config import FinanzOnlineConfig
from finanzonline_uid.domain.errors import AuthenticationError, QueryError
from finanzonline_uid.domain.models import FinanzOnlineCredentials, UidCheckResult

_PROMPT = "Enter EU VAT ID to verify: "
_SAVED = "Result saved to: "
_COUNTDOWN = "Next attempt in"
#: Retry interval small enough to keep the test fast; the countdown still draws one frame.
_RETRY_MINUTES = "0.001"


class _ScriptedChecker:
    """A use case whose attempts return (or raise) the given outcomes in turn.

    The CLI builds a new use case for every attempt, so the list is shared, not
    copied: each attempt consumes the next outcome.
    """

    def __init__(self, outcomes: list[UidCheckResult | Exception]) -> None:
        self._outcomes = outcomes

    def execute(self, credentials: FinanzOnlineCredentials, uid_tn: str, target_uid: str) -> UidCheckResult:
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _valid() -> UidCheckResult:
    return UidCheckResult(uid="DE123456789", return_code=0, message="UID is valid", timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc))


def _busy() -> QueryError:
    return QueryError("Service unavailable", return_code=1511, retryable=True)


def _check(args: list[str], output_format: str, outcomes: list[UidCheckResult | Exception], *, stdin: str | None = None) -> Result:
    """Run ``check <args> --no-email --format <output_format>`` with a scripted use case."""
    credentials = FinanzOnlineCredentials(tid="123456789", benid="TESTUSER", pin="testpin", herstellerid="ATU12345678")
    fo_config = FinanzOnlineConfig(credentials=credentials, uid_tn="ATU12345678", cache_results_hours=0, ratelimit_queries=0)

    def load_config(*, profile: str | None = None) -> Config:
        return Config({}, {})

    def load_fo_config(_config: Config) -> FinanzOnlineConfig:
        return fo_config

    def build_uid_checker(_fo_config: FinanzOnlineConfig, _notifier: cli_mod.RateLimitNotifier) -> cli_mod.UidChecker:
        return _ScriptedChecker(outcomes)

    deps = dataclasses.replace(
        cli_mod.production_dependencies(),
        load_config=load_config,
        load_finanzonline_config=load_fo_config,
        build_uid_checker=build_uid_checker,
    )
    return CliRunner().invoke(cli_mod.cli, ["check", *args, "--no-email", "--format", output_format], obj=deps, input=stdin)


def _document(result: Result) -> dict[str, Any]:
    """The whole stdout parsed as one JSON document; anything beside it makes json.loads fail."""
    parsed: dict[str, Any] = json.loads(result.stdout)
    return parsed


@pytest.mark.os_agnostic
def test_json_outputdir_success_keeps_the_saved_note_off_stdout(tmp_path: Path) -> None:
    result = _check(["DE123456789", "--outputdir", str(tmp_path)], "json", [_valid()])

    assert result.exit_code == 0
    assert _document(result)["uid"] == "DE123456789"
    saved = tmp_path / "DE123456789_2026-01-02.html"
    assert saved.is_file()
    assert f"{_SAVED}{saved}\n" in result.stderr


@pytest.mark.os_agnostic
def test_json_interactive_success_keeps_the_prompt_off_stdout() -> None:
    result = _check(["--interactive"], "json", [_valid()], stdin="de 123456789\n")

    assert result.exit_code == 0
    assert _document(result)["uid"] == "DE123456789"
    assert result.stderr.startswith(_PROMPT)


@pytest.mark.os_agnostic
def test_json_retry_success_keeps_prompt_and_countdown_off_stdout(tmp_path: Path) -> None:
    args = ["--interactive", "--retryminutes", _RETRY_MINUTES, "--outputdir", str(tmp_path)]
    result = _check(args, "json", [_busy(), _valid()], stdin="DE123456789\n")

    assert result.exit_code == 0
    assert _document(result)["is_valid"] is True
    assert (_PROMPT in result.stderr, _COUNTDOWN in result.stderr, _SAVED in result.stderr) == (True, True, True)


@pytest.mark.os_agnostic
def test_json_retry_failure_is_one_error_record_on_stdout() -> None:
    result = _check(
        ["--interactive", "--retryminutes", _RETRY_MINUTES], "json", [_busy(), AuthenticationError("Not authorized", return_code=-4)], stdin="DE123456789\n"
    )

    assert result.exit_code == 3
    record = _document(result)
    assert (record["error"], record["error_type"], record["uid"]) == (True, "Authentication Error", "DE123456789")
    assert (_PROMPT in result.stderr, _COUNTDOWN in result.stderr) == (True, True)


@pytest.mark.os_agnostic
def test_human_mode_keeps_prompt_countdown_and_saved_note_on_stdout(tmp_path: Path) -> None:
    args = ["--interactive", "--retryminutes", _RETRY_MINUTES, "--outputdir", str(tmp_path)]
    result = _check(args, "human", [_busy(), _valid()], stdin="DE123456789\n")

    assert result.exit_code == 0
    assert result.stdout.startswith(_PROMPT)
    assert (_COUNTDOWN in result.stdout, _SAVED in result.stdout) == (True, True)
    assert (_PROMPT in result.stderr, _COUNTDOWN in result.stderr, _SAVED in result.stderr) == (False, False, False)
