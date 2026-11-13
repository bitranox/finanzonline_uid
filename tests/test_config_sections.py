"""Configuration sections: how each one is read, and what reaches the user while reading it.

Two properties need a real CLI run to show: a mistyped ``output_dir`` must reach the user as a
configuration error (exit 2) instead of silently switching result files off, and reading ``[app]``
must write nothing, since the CLI reads it before logging is initialised and any record emitted
then goes out unformatted through ``logging.lastResort``. Those tests run the CLI as a subprocess
with every app setting and the conftest's ``.env`` scrubbed out, keeping the conftest's layer
redirects, and starting in an empty ``tmp_path`` so no ``.env`` is discovered.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from layer_roots import SYSTEM_LAYER_ROOT_VARIABLES, USER_LAYER_ROOT_VARIABLES
from lib_layered_config import Config, read_config
from pydantic import ValidationError

from finanzonline_uid import __init__conf__, mail
from finanzonline_uid.config import empty_text_list, read_config_section, text_setting
from finanzonline_uid.enums import ConfigSection
from finanzonline_uid.logging_setup import build_runtime_config

pytestmark = pytest.mark.os_agnostic

_ENV_PREFIX = f"{__init__conf__.LAYEREDCONF_SLUG.upper().replace('-', '_')}___"


def _scrubbed_env(**settings: str) -> dict[str, str]:
    """This process's environment minus every app setting, plus `settings` as app settings."""
    env = {name: value for name, value in os.environ.items() if not name.startswith((_ENV_PREFIX, "LOG_"))}
    redirected = SYSTEM_LAYER_ROOT_VARIABLES + USER_LAYER_ROOT_VARIABLES
    missing = [name for name in redirected if name not in env]
    assert not missing, f"layer redirects not set by the conftest: {missing}"
    env.update({f"{_ENV_PREFIX}{name}": value for name, value in settings.items()})
    return env


def _run_cli(tmp_path: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "finanzonline_uid", *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


def test_a_boolean_output_dir_from_the_environment_arrives_as_a_bool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Premise of the CLI test below: without it, that test would not exercise a mistyped value.
    monkeypatch.setenv(f"{_ENV_PREFIX}FINANZONLINE__OUTPUT_DIR", "true")

    config = read_config(
        vendor=__init__conf__.LAYEREDCONF_VENDOR,
        app=__init__conf__.LAYEREDCONF_APP,
        slug=__init__conf__.LAYEREDCONF_SLUG,
        start_dir=str(tmp_path),
    )

    assert read_config_section(config, ConfigSection.FINANZONLINE)["output_dir"] is True


@pytest.mark.parametrize("output_format", ["human", "json"])
def test_check_with_a_boolean_output_dir_exits_with_a_configuration_error(tmp_path: Path, output_format: str) -> None:
    # uid_tn is invalid on purpose: should the output_dir refusal ever stop firing, the run still
    # ends on a configuration error before any network call, and the stderr assertion catches it.
    env = _scrubbed_env(
        FINANZONLINE__TID="123456789",
        FINANZONLINE__BENID="987654321",
        FINANZONLINE__PIN="47110815",
        FINANZONLINE__HERSTELLERID="ATU12345678",
        FINANZONLINE__UID_TN="XX12345678",
        FINANZONLINE__OUTPUT_DIR="true",
    )

    completed = _run_cli(tmp_path, env, "check", "ATU12345678", "--no-email", "--format", output_format)

    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "finanzonline.output_dir: must be a directory path given as text, got bool" in completed.stderr


def test_an_unsupported_language_writes_nothing_before_logging_starts(tmp_path: Path) -> None:
    env = _scrubbed_env(APP__LANGUAGE="xx")

    completed = _run_cli(tmp_path, env, "hello")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "language" not in completed.stderr.lower()
    assert "Hello" in completed.stdout


@pytest.mark.parametrize("section", list(ConfigSection))
def test_each_section_is_read_by_its_name(section: ConfigSection) -> None:
    config = Config({member.value: {"marker": member.value} for member in ConfigSection}, {})

    assert read_config_section(config, section) == {"marker": section.value}


def test_text_setting_is_the_single_coercion_the_mail_section_uses() -> None:
    section = mail.EmailSection.model_validate({"smtp_username": 123456, "smtp_password": True})

    assert (section.smtp_username, section.smtp_password) == (text_setting(123456), text_setting(True))
    assert mail.EmailConfig().smtp_hosts == empty_text_list()


@pytest.mark.parametrize("key", ["service", "environment"])
def test_a_logging_name_that_is_not_text_is_refused_with_the_operator_s_value(key: str) -> None:
    config = Config({ConfigSection.LIB_LOG_RICH.value: {key: True}}, {})

    with pytest.raises(ValidationError) as excinfo:
        build_runtime_config(config)

    (detail,) = excinfo.value.errors()
    assert (detail["loc"], detail["input"]) == ((key,), True)


def test_absent_logging_names_take_their_defaults() -> None:
    runtime = build_runtime_config(Config({}, {}))

    assert (runtime.service, runtime.environment) == (__init__conf__.name, "prod")
