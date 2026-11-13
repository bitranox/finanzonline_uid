"""``check`` with no FinanzOnline credentials anywhere exits 2 in every output format.

The CLI runs as a subprocess with a scrubbed environment: ``tests/conftest.py`` loads the repo's
``.env`` into this process, so an in-process run could pick up real credentials and query the live
service. The child keeps the conftest's layer redirects (all under ``tmp_path``) and starts in an
empty ``tmp_path`` so no ``.env`` is discovered either.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from layer_roots import SYSTEM_LAYER_ROOT_VARIABLES, USER_LAYER_ROOT_VARIABLES

from finanzonline_uid import __init__conf__

_ENV_PREFIX = f"{__init__conf__.LAYEREDCONF_SLUG.upper().replace('-', '_')}___"


def _env_without_credentials() -> dict[str, str]:
    """This process's environment minus every app setting and logging override."""
    env = {name: value for name, value in os.environ.items() if not name.startswith((_ENV_PREFIX, "LOG_"))}
    redirected = SYSTEM_LAYER_ROOT_VARIABLES + USER_LAYER_ROOT_VARIABLES
    missing = [name for name in redirected if name not in env]
    assert not missing, f"layer redirects not set by the conftest: {missing}"
    return env


@pytest.mark.os_agnostic
@pytest.mark.parametrize("output_format", ["human", "json"])
def test_check_without_any_credentials_exits_two(tmp_path: Path, output_format: str) -> None:
    env = _env_without_credentials()

    completed = subprocess.run(
        [sys.executable, "-m", "finanzonline_uid", "check", "ATU12345678", "--no-email", "--format", output_format],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )

    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "finanzonline.tid" in completed.stderr
