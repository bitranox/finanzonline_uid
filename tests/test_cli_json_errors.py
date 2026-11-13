"""``check --format json`` reports every failure as one JSON error record on stdout.

The human-readable lines on stderr and the exit code are the same as with ``--format human``,
and with ``--format human`` stdout stays empty on failure. The collaborators are injected
through Click's ``obj`` (:class:`finanzonline_uid.cli.CliDependencies`), so nothing here reaches
FinanzOnline or a mail server.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Iterator
from typing import Any

import pytest
from click.testing import CliRunner, Result
from lib_layered_config import Config

from finanzonline_uid import cli as cli_mod
from finanzonline_uid.config import FinanzOnlineConfig
from finanzonline_uid.domain.errors import AuthenticationError, ConfigurationError, QueryError
from finanzonline_uid.domain.models import FinanzOnlineCredentials, UidCheckResult
from finanzonline_uid.enums import Language
from finanzonline_uid.i18n import setup_locale


class _ScriptedChecker:
    """A use case whose attempts return (or raise) the given outcomes in turn."""

    def __init__(self, outcomes: list[UidCheckResult | BaseException]) -> None:
        self._outcomes = list(outcomes)

    def execute(self, credentials: FinanzOnlineCredentials, uid_tn: str, target_uid: str) -> UidCheckResult:
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _fo_config() -> FinanzOnlineConfig:
    """FinanzOnline settings with cache, rate limit and file output switched off."""
    credentials = FinanzOnlineCredentials(tid="123456789", benid="TESTUSER", pin="testpin", herstellerid="ATU12345678")
    return FinanzOnlineConfig(credentials=credentials, uid_tn="ATU12345678", cache_results_hours=0, ratelimit_queries=0)


def _dependencies(
    outcomes: list[UidCheckResult | BaseException],
    *,
    fo_config_error: ConfigurationError | None = None,
    language: str | None = None,
) -> cli_mod.CliDependencies:
    """Collaborators with an empty configuration (or only ``[app] language``) and a scripted use case."""

    def load_config(*, profile: str | None = None) -> Config:
        if language is None:
            return Config({}, {})
        return Config({"app": {"language": language}}, {})

    def load_fo_config(_config: Config) -> FinanzOnlineConfig:
        if fo_config_error is not None:
            raise fo_config_error
        return _fo_config()

    def build_uid_checker(_fo_config: FinanzOnlineConfig, _notifier: cli_mod.RateLimitNotifier) -> cli_mod.UidChecker:
        return _ScriptedChecker(outcomes)

    return dataclasses.replace(
        cli_mod.production_dependencies(),
        load_config=load_config,
        load_finanzonline_config=load_fo_config,
        build_uid_checker=build_uid_checker,
    )


def _check(
    args: list[str],
    output_format: str,
    *,
    outcomes: list[UidCheckResult | BaseException] | None = None,
    fo_config_error: ConfigurationError | None = None,
    stdin: str | None = None,
    language: str | None = None,
) -> Result:
    """Run ``check <args> --no-email --format <output_format>`` in-process."""
    deps = _dependencies(outcomes or [], fo_config_error=fo_config_error, language=language)
    return CliRunner().invoke(cli_mod.cli, ["check", *args, "--no-email", "--format", output_format], obj=deps, input=stdin)


#: The --interactive prompt with the typed input CliRunner echoes after it: on stdout with
#: --format human, on stderr with --format json (stdout then carries only the JSON document).
_PROMPT_ECHO = re.compile(r"\AEnter EU VAT ID to verify: [^\n]*\n")
#: The console log handler writes to the stderr of the first run in this process only, so log
#: lines say nothing about one run against another and are left out of the comparison.
_LOG_LINE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]\[[A-Z]+\]: .*\n", re.MULTILINE)


def _stdout_after_prompt(result: Result) -> str:
    """Stdout without the interactive prompt line (present only with ``--interactive --format human``)."""
    return _PROMPT_ECHO.sub("", result.stdout)


def _stderr_without_log_lines(result: Result) -> str:
    """Stderr as the command wrote it, without console log lines."""
    return _LOG_LINE.sub("", result.stderr)


def _record(result: Result) -> dict[str, Any]:
    """The one JSON document on stdout, parsed whole (``json.loads`` refuses anything beside it)."""
    parsed: dict[str, Any] = json.loads(result.stdout)
    return parsed


#: Each failure the command reports, as (case id, check args, scripted outcomes, stdin).
_FAILURES: list[tuple[str, list[str], list[UidCheckResult | BaseException], str | None]] = [
    ("authentication", ["DE123456789"], [AuthenticationError("Not authorized", return_code=-4)], None),
    ("query", ["DE123456789"], [QueryError("Rate limit exceeded", return_code=1513, retryable=True)], None),
    ("unexpected", ["DE123456789"], [RuntimeError("socket exploded")], None),
    ("missing-uid", [], [], None),
    ("retryminutes-without-interactive", ["DE123456789", "--retryminutes", "1"], [], None),
    ("cancelled-in-retry-loop", ["--interactive", "--retryminutes", "0"], [KeyboardInterrupt()], "DE123456789\n"),
    ("cancelled-single-attempt", ["DE123456789"], [KeyboardInterrupt()], None),
]


@pytest.mark.os_agnostic
def test_json_authentication_failure_is_one_record_on_stdout() -> None:
    result = _check(["DE123456789"], "json", outcomes=[AuthenticationError("Not authorized", return_code=-4)])

    assert result.exit_code == 3
    record = _record(result)
    assert (record["uid"], record["error_type"], record["message"], record["return_code"]) == ("DE123456789", "Authentication Error", "Not authorized", -4)
    assert "\nAuthentication Error: Not authorized" in result.stderr


@pytest.mark.os_agnostic
def test_json_query_failure_is_one_record_on_stdout() -> None:
    result = _check(["DE123456789"], "json", outcomes=[QueryError("Rate limit exceeded", return_code=1513, retryable=True)])

    assert result.exit_code == 4
    record = _record(result)
    assert (record["error_type"], record["return_code"], record["retryable"]) == ("Query Error", 1513, True)
    assert "This error may be temporary. Try again later." in result.stderr


@pytest.mark.os_agnostic
def test_json_configuration_failure_is_one_record_on_stdout() -> None:
    result = _check(["DE123456789"], "json", fo_config_error=ConfigurationError("Missing TID"))

    assert result.exit_code == 2
    assert (_record(result)["error_type"], _record(result)["message"]) == ("Configuration Error", "Missing TID")


@pytest.mark.os_agnostic
def test_json_unexpected_failure_is_a_record_and_still_propagates() -> None:
    """The unexpected exception keeps reaching lib_cli_exit_tools, which prints it and picks the exit code."""
    result = _check(["DE123456789"], "json", outcomes=[RuntimeError("socket exploded")])

    assert isinstance(result.exception, RuntimeError)
    assert (_record(result)["error_type"], _record(result)["message"], _record(result)["uid"]) == ("Unexpected Error", "socket exploded", "DE123456789")


@pytest.mark.os_agnostic
def test_json_missing_uid_refusal_is_a_record_with_an_empty_uid() -> None:
    result = _check([], "json")

    assert result.exit_code == 2
    assert _stderr_without_log_lines(result) == "Error: UID argument is required (or use --interactive)\n"
    record = _record(result)
    assert (record["uid"], record["error_type"], record["message"]) == ("", "Validation Error", "UID argument is required (or use --interactive)")


@pytest.mark.os_agnostic
def test_json_retryminutes_refusal_is_a_record_naming_the_given_uid() -> None:
    result = _check(["de 123456789", "--retryminutes", "1"], "json")

    assert result.exit_code == 2
    assert _stderr_without_log_lines(result) == "Error: --retryminutes requires --interactive mode\n"
    record = _record(result)
    assert (record["uid"], record["error_type"], record["message"]) == ("DE123456789", "Validation Error", "--retryminutes requires --interactive mode")


@pytest.fixture
def english_afterwards() -> Iterator[None]:
    """Put the process back on English: a localized run leaves the module-level locale switched."""
    yield
    setup_locale(Language.EN)


_E_ACUTE = "\N{LATIN SMALL LETTER E WITH ACUTE}"

#: Each refusal per locale, as (language, check args, uid in the record, stderr line, record message).
#: French puts a space before the colon of its "Erreur :" lead-in, so a record message cut out of
#: the stderr line by prefix kept the lead-in there; the other locales pin that nothing moved.
_LOCALIZED_REFUSALS: list[tuple[str, list[str], str, str, str]] = [
    ("en", [], "", "Error: UID argument is required (or use --interactive)", "UID argument is required (or use --interactive)"),
    ("de", [], "", "Fehler: UID-Argument erforderlich (oder --interactive verwenden)", "UID-Argument erforderlich (oder --interactive verwenden)"),
    ("es", [], "", "Error: El argumento UID es requerido (o use --interactive)", "El argumento UID es requerido (o use --interactive)"),
    ("fr", [], "", "Erreur : L'argument UID est requis (ou utilisez --interactive)", "L'argument UID est requis (ou utilisez --interactive)"),
    (
        "en",
        ["DE123456789", "--retryminutes", "1"],
        "DE123456789",
        "Error: --retryminutes requires --interactive mode",
        "--retryminutes requires --interactive mode",
    ),
    (
        "de",
        ["DE123456789", "--retryminutes", "1"],
        "DE123456789",
        "Fehler: --retryminutes erfordert --interactive Modus",
        "--retryminutes erfordert --interactive Modus",
    ),
    (
        "es",
        ["DE123456789", "--retryminutes", "1"],
        "DE123456789",
        "Error: --retryminutes requiere modo --interactive",
        "--retryminutes requiere modo --interactive",
    ),
    (
        "fr",
        ["DE123456789", "--retryminutes", "1"],
        "DE123456789",
        f"Erreur : --retryminutes n{_E_ACUTE}cessite le mode --interactive",
        f"--retryminutes n{_E_ACUTE}cessite le mode --interactive",
    ),
]


@pytest.mark.os_agnostic
@pytest.mark.usefixtures("english_afterwards")
@pytest.mark.parametrize(
    ("language", "args", "uid", "stderr_line", "record_message"),
    _LOCALIZED_REFUSALS,
    ids=[f"{case[0]}-{'retryminutes' if case[1] else 'missing-uid'}" for case in _LOCALIZED_REFUSALS],
)
def test_json_refusal_record_carries_the_bare_reason_in_every_locale(language: str, args: list[str], uid: str, stderr_line: str, record_message: str) -> None:
    result = _check(args, "json", language=language)

    assert result.exit_code == 2
    assert _stderr_without_log_lines(result) == stderr_line + "\n"
    record = _record(result)
    assert (record["uid"], record["error_type"], record["message"]) == (uid, "Validation Error", record_message)


@pytest.mark.os_agnostic
@pytest.mark.usefixtures("english_afterwards")
@pytest.mark.parametrize("language", list(Language))
def test_every_refusal_has_a_distinct_record_message_in_every_locale(language: Language) -> None:
    setup_locale(language)

    for refusal in cli_mod.CheckRefusal:
        assert refusal.record_message() not in ("", refusal.stderr_line())
        assert refusal.stderr_line().endswith(refusal.record_message())


@pytest.mark.os_agnostic
def test_json_cancellation_in_the_retry_loop_is_one_record() -> None:
    result = _check(["--interactive", "--retryminutes", "0"], "json", outcomes=[KeyboardInterrupt()], stdin="DE123456789\n")

    assert result.exit_code == 4
    record = _record(result)
    assert (record["uid"], record["error_type"], record["message"]) == ("DE123456789", "Cancelled", "Check cancelled by user")


@pytest.mark.os_agnostic
def test_json_ctrl_c_outside_the_retry_loop_is_a_cancelled_record() -> None:
    result = _check(["DE123456789"], "json", outcomes=[KeyboardInterrupt()])

    assert (_record(result)["error_type"], _record(result)["uid"]) == ("Cancelled", "DE123456789")


@pytest.mark.os_agnostic
@pytest.mark.parametrize(("args", "outcomes", "stdin"), [case[1:] for case in _FAILURES], ids=[case[0] for case in _FAILURES])
def test_human_failure_leaves_stdout_empty(args: list[str], outcomes: list[UidCheckResult | BaseException], stdin: str | None) -> None:
    """Only a JSON caller gets the record; the human format prints nothing on stdout when it fails."""
    result = _check(args, "human", outcomes=outcomes, stdin=stdin)

    assert result.exit_code != 0
    assert _stdout_after_prompt(result) == ""


@pytest.mark.os_agnostic
@pytest.mark.parametrize(("args", "outcomes", "stdin"), [case[1:] for case in _FAILURES], ids=[case[0] for case in _FAILURES])
def test_json_failure_keeps_the_human_stderr_and_exit_code(args: list[str], outcomes: list[UidCheckResult | BaseException], stdin: str | None) -> None:
    """``--format json`` only adds the stdout record: stderr, exit code and exception match the human run.

    The one difference is the --interactive prompt, which the json run writes to stderr so
    stdout stays a single JSON document.
    """
    human = _check(args, "human", outcomes=list(outcomes), stdin=stdin)
    machine = _check(args, "json", outcomes=list(outcomes), stdin=stdin)

    assert (_PROMPT_ECHO.sub("", _stderr_without_log_lines(machine)), machine.exit_code, type(machine.exception)) == (
        _stderr_without_log_lines(human),
        human.exit_code,
        type(human.exception),
    )
    assert _record(machine)["error"] is True
