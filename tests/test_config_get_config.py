"""``get_config`` reads every layer again on each call.

Its result depends on the environment variables and, through ``.env`` discovery, on the
current directory; neither is part of its arguments. A call made after either changed must
see the change, so the function holds no result between calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from finanzonline_uid.config import get_config

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.os_agnostic

_PROBE_VARIABLE = "FINANZONLINE_UID___GET_CONFIG_PROBE__VALUE"


def test_a_second_call_sees_an_environment_variable_set_after_the_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_PROBE_VARIABLE, "first")
    first = get_config(start_dir=str(tmp_path))
    monkeypatch.setenv(_PROBE_VARIABLE, "second")

    second = get_config(start_dir=str(tmp_path))

    assert (first.get("get_config_probe.value"), second.get("get_config_probe.value")) == ("first", "second")
