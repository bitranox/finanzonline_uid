"""``check --outputdir`` reads its value with the rule ``finanzonline.output_dir`` is read with.

An empty or whitespace-only argument names no directory: it means the option was not given, so
the configured directory (or none) applies. It must not become a directory named with spaces, nor
the current directory (``Path("")`` is ``Path(".")``). Collaborators come in through Click's ``obj``.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner, Result
from lib_layered_config import Config

from finanzonline_uid import cli as cli_mod
from finanzonline_uid.config import FinanzOnlineConfig
from finanzonline_uid.domain.models import FinanzOnlineCredentials, UidCheckResult

_SAVED_FILE = "DE123456789_2026-01-02.html"
_BLANK_VALUES = ["", "   ", " \t "]


class _ValidChecker:
    """A use case that finds every UID valid."""

    def execute(self, credentials: FinanzOnlineCredentials, uid_tn: str, target_uid: str) -> UidCheckResult:
        return UidCheckResult(uid=target_uid, return_code=0, message="UID is valid", timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc))


def _check(outputdir: str, *, configured_dir: Path | None = None) -> Result:
    """Run ``check DE123456789 --no-email --outputdir <outputdir>``."""
    credentials = FinanzOnlineCredentials(tid="123456789", benid="TESTUSER", pin="testpin", herstellerid="ATU12345678")
    fo_config = FinanzOnlineConfig(credentials=credentials, uid_tn="ATU12345678", cache_results_hours=0, ratelimit_queries=0, output_dir=configured_dir)

    def load_config(*, profile: str | None = None) -> Config:
        return Config({}, {})

    def load_fo_config(_config: Config) -> FinanzOnlineConfig:
        return fo_config

    def build_uid_checker(_fo_config: FinanzOnlineConfig, _notifier: cli_mod.RateLimitNotifier) -> cli_mod.UidChecker:
        return _ValidChecker()

    deps = dataclasses.replace(
        cli_mod.production_dependencies(),
        load_config=load_config,
        load_finanzonline_config=load_fo_config,
        build_uid_checker=build_uid_checker,
    )
    return CliRunner().invoke(cli_mod.cli, ["check", "DE123456789", "--no-email", "--outputdir", outputdir], obj=deps)


@pytest.mark.os_agnostic
@pytest.mark.parametrize("blank", _BLANK_VALUES, ids=repr)
def test_blank_outputdir_writes_no_file(blank: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = _check(blank)

    assert result.exit_code == 0
    assert list(tmp_path.iterdir()) == []
    assert "Result saved to" not in result.output


@pytest.mark.os_agnostic
@pytest.mark.parametrize("blank", _BLANK_VALUES, ids=repr)
def test_blank_outputdir_leaves_the_configured_directory_in_force(blank: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    configured = tmp_path / "configured"

    result = _check(blank, configured_dir=configured)

    assert result.exit_code == 0
    assert [path.relative_to(tmp_path).as_posix() for path in sorted(tmp_path.rglob("*"))] == ["configured", f"configured/{_SAVED_FILE}"]


@pytest.mark.os_agnostic
def test_explicit_dot_outputdir_still_means_the_current_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only a value that names no path is dropped; "." names the current directory."""
    monkeypatch.chdir(tmp_path)

    result = _check(".")

    assert result.exit_code == 0
    assert [path.name for path in tmp_path.iterdir()] == [_SAVED_FILE]
