"""Digit-only ``.env`` values reach every text setting as the text the operator wrote.

lib_layered_config reads an unquoted ``.env`` or environment value as an int whenever that number
reads back as the same text (``123456`` -> ``123456``). A text setting must accept such a number and
keep its digits: an SMTP password of only digits must not be dropped as "not a string", and a
digit-only logging name must not make lib_log_rich refuse its settings at startup.

Each test loads a real ``.env`` through the real loader and asserts the library hands over an int
first, so a change in its coercion shows up here rather than on a deployed host.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from lib_layered_config import Config, read_config

from finanzonline_uid import __init__conf__
from finanzonline_uid.config import load_finanzonline_config
from finanzonline_uid.logging_setup import build_runtime_config
from finanzonline_uid.mail import load_email_config

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.os_agnostic


def _config_from_dotenv(tmp_path: Path, body: str) -> Config:
    env_file = tmp_path / "test.env"
    env_file.write_text(body, encoding="utf-8")
    return read_config(
        vendor=__init__conf__.LAYEREDCONF_VENDOR,
        app=__init__conf__.LAYEREDCONF_APP,
        slug=__init__conf__.LAYEREDCONF_SLUG,
        start_dir=str(tmp_path),
        dotenv_path=str(env_file),
    )


def test_a_digit_only_smtp_username_reaches_the_mail_config_as_its_text(tmp_path: Path) -> None:
    config = _config_from_dotenv(tmp_path, "EMAIL__SMTP_USERNAME=123456\n")
    # Premise: the library hands the value over as a number. Without it the test proves nothing.
    assert isinstance(config.get("email", default={})["smtp_username"], int)

    assert load_email_config(config).smtp_username == "123456"


def test_a_digit_only_smtp_password_reaches_the_mail_config_as_its_text(tmp_path: Path) -> None:
    config = _config_from_dotenv(tmp_path, "EMAIL__SMTP_PASSWORD=123456\n")
    assert isinstance(config.get("email", default={})["smtp_password"], int)

    password = load_email_config(config).smtp_password

    assert password is not None and password.get_secret_value() == "123456"


@pytest.mark.parametrize("key", ["service", "environment"])
def test_a_digit_only_logging_name_reaches_lib_log_rich_as_its_text(tmp_path: Path, key: str) -> None:
    config = _config_from_dotenv(tmp_path, f"LIB_LOG_RICH__{key.upper()}=4711\n")
    assert isinstance(config.get("lib_log_rich", default={})[key], int)

    assert getattr(build_runtime_config(config), key) == "4711"


def test_a_digit_only_credential_still_loads_as_text(tmp_path: Path) -> None:
    config = _config_from_dotenv(
        tmp_path,
        "FINANZONLINE__TID=123456789\nFINANZONLINE__BENID=987654321\nFINANZONLINE__PIN=47110815\n"
        "FINANZONLINE__HERSTELLERID=ATU12345678\nFINANZONLINE__UID_TN=ATU12345678\n",
    )
    assert isinstance(config.get("finanzonline", default={})["tid"], int)

    credentials = load_finanzonline_config(config).credentials

    assert (credentials.tid, credentials.benid, credentials.pin) == ("123456789", "987654321", "47110815")


def test_a_numeric_setting_still_reads_as_a_number(tmp_path: Path) -> None:
    config = _config_from_dotenv(tmp_path, "EMAIL__TIMEOUT=45\n")

    assert load_email_config(config).timeout == 45.0


def test_a_boolean_is_not_taken_as_a_text_setting(tmp_path: Path) -> None:
    config = _config_from_dotenv(tmp_path, "EMAIL__SMTP_PASSWORD=true\n")
    assert config.get("email", default={})["smtp_password"] is True

    assert load_email_config(config).smtp_password is None


def test_a_digit_only_output_dir_keeps_its_digits(tmp_path: Path) -> None:
    config = _config_from_dotenv(
        tmp_path,
        "FINANZONLINE__TID=123456789\nFINANZONLINE__BENID=987654321\nFINANZONLINE__PIN=47110815\n"
        "FINANZONLINE__HERSTELLERID=ATU12345678\nFINANZONLINE__UID_TN=ATU12345678\nFINANZONLINE__OUTPUT_DIR=2024\n",
    )
    assert isinstance(config.get("finanzonline", default={})["output_dir"], int)

    output_dir = load_finanzonline_config(config).output_dir

    assert output_dir is not None and output_dir.name == "2024"
