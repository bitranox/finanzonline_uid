"""Module entry stories ensuring `python -m` mirrors the console script."""

from __future__ import annotations

import importlib
import runpy
import sys
from collections.abc import Callable

import lib_cli_exit_tools
import pytest

from finanzonline_uid import cli as cli_mod


@pytest.mark.os_agnostic
@pytest.mark.parametrize(
    "argv",
    [["--bad-flag"], ["no-such-command"], ["check", "--bad-flag"], ["--help"], ["hello"]],
    ids=["bad-flag", "unknown-command", "bad-subcommand-flag", "help", "hello"],
)
def test_module_entry_exits_with_the_code_the_console_script_gives(monkeypatch: pytest.MonkeyPatch, isolated_traceback_config: None, argv: list[str]) -> None:
    script_code = cli_mod.main(argv)
    monkeypatch.setattr(sys, "argv", ["finanzonline_uid", *argv])

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("finanzonline_uid.__main__", run_name="__main__")

    assert exc.value.code == script_code


@pytest.mark.os_agnostic
def test_module_entry_reports_a_usage_error_with_the_click_usage_code(monkeypatch: pytest.MonkeyPatch, isolated_traceback_config: None) -> None:
    monkeypatch.setattr(sys, "argv", ["finanzonline_uid", "--bad-flag"])

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("finanzonline_uid.__main__", run_name="__main__")

    assert exc.value.code == 2


@pytest.mark.os_agnostic
def test_when_traceback_flag_is_used_via_module_entry_the_full_poem_is_printed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    strip_ansi: Callable[[str], str],
) -> None:
    """Verify --traceback via module entry prints full traceback on error."""
    monkeypatch.setattr(sys, "argv", ["finanzonline_uid", "--traceback", "fail"])
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback", False, raising=False)
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback_force_color", False, raising=False)

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("finanzonline_uid.__main__", run_name="__main__")

    plain_err = strip_ansi(capsys.readouterr().err)

    assert exc.value.code != 0
    assert "Traceback (most recent call last)" in plain_err
    assert "RuntimeError: I should fail" in plain_err
    assert "[TRUNCATED" not in plain_err
    assert lib_cli_exit_tools.config.traceback is False
    assert lib_cli_exit_tools.config.traceback_force_color is False


@pytest.mark.os_agnostic
def test_when_the_module_is_imported_it_runs_nothing() -> None:
    # Left imported, every later runpy of finanzonline_uid.__main__ warns that it is already loaded.
    previous = sys.modules.pop("finanzonline_uid.__main__", None)
    try:
        module = importlib.import_module("finanzonline_uid.__main__")

        assert module.cli is cli_mod
    finally:
        sys.modules.pop("finanzonline_uid.__main__", None)
        if previous is not None:
            sys.modules["finanzonline_uid.__main__"] = previous
