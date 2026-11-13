"""``check`` with no FinanzOnline credentials anywhere exits 2 in every output format.

With ``--format json`` the failure also reaches stdout as one JSON error record, so a caller parsing
stdout gets it; the human-readable stderr text is the same in both formats.

The CLI runs as a subprocess with a scrubbed environment: ``tests/conftest.py`` loads the repo's
``.env`` into this process, so an in-process run could pick up real credentials and query the live
service. The child keeps the conftest's layer redirects (all under ``tmp_path``) and starts in an
empty ``tmp_path`` so no ``.env`` is discovered either.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from layer_roots import SYSTEM_LAYER_ROOT_VARIABLES, USER_LAYER_ROOT_VARIABLES
from log_lines import LOG_LINE, PINNED_CONSOLE_LAYOUT

from finanzonline_uid import __init__conf__

_ENV_PREFIX = f"{__init__conf__.LAYEREDCONF_SLUG.upper().replace('-', '_')}___"


def _env_without_credentials() -> dict[str, str]:
    """This process's environment minus every app setting and logging override.

    The console layout is then pinned, so the log line the stderr comparison filters out has the
    shape ``LOG_LINE`` matches on Windows too, where lib_log_rich's default layout differs.
    """
    env = {name: value for name, value in os.environ.items() if not name.startswith((_ENV_PREFIX, "LOG_"))}
    redirected = SYSTEM_LAYER_ROOT_VARIABLES + USER_LAYER_ROOT_VARIABLES
    missing = [name for name in redirected if name not in env]
    assert not missing, f"layer redirects not set by the conftest: {missing}"
    return env | PINNED_CONSOLE_LAYOUT


def _check_without_credentials(cwd: Path, output_format: str) -> subprocess.CompletedProcess[str]:
    """Run ``check ATU12345678 --no-email --format <output_format>`` with no credentials anywhere."""
    return subprocess.run(
        [sys.executable, "-m", "finanzonline_uid", "check", "ATU12345678", "--no-email", "--format", output_format],
        cwd=cwd,
        env=_env_without_credentials(),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


@pytest.mark.os_agnostic
@pytest.mark.parametrize("output_format", ["human", "json"])
def test_check_without_any_credentials_exits_two(tmp_path: Path, output_format: str) -> None:
    completed = _check_without_credentials(tmp_path, output_format)

    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "finanzonline.tid" in completed.stderr
    if output_format == "json":
        record = json.loads(completed.stdout)
        assert (record["error_type"], record["uid"], record["error"]) == ("Configuration Error", "ATU12345678", True)
        assert "finanzonline.tid" in record["message"]
    else:
        assert completed.stdout == ""


@pytest.mark.os_agnostic
def test_check_without_any_credentials_prints_the_same_stderr_in_both_formats(tmp_path: Path) -> None:
    """The JSON record is added on stdout only; the stderr text a person reads does not change."""
    human = _check_without_credentials(tmp_path, "human")
    machine = _check_without_credentials(tmp_path, "json")

    assert LOG_LINE.sub("", machine.stderr) == LOG_LINE.sub("", human.stderr)
    assert "Configure FinanzOnline credentials" in human.stderr
    assert LOG_LINE.search(human.stderr) is not None, "the log line filter no longer matches anything"
