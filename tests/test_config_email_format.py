"""``[finanzonline].email_format`` is read the same way by both of its readers.

``load_email_format`` reads the one key for the error email of a run whose
section failed to load; ``load_finanzonline_config`` reads it with the rest of
the section. Both must agree on every value, and neither turns an unusable
value into a refusal: it means HTML.
"""

from __future__ import annotations

from typing import Any

import pytest
from lib_layered_config import Config

from finanzonline_uid.config import load_email_format, load_finanzonline_config
from finanzonline_uid.domain.errors import ConfigurationError
from finanzonline_uid.enums import EmailFormat

_CREDENTIALS: dict[str, Any] = {
    "tid": "123456789",
    "benid": "TESTUSER",
    "pin": "secretpin",
    "uid_tn": "ATU12345678",
    "herstellerid": "ATU12345678",
}

#: Values that name a format, in the spellings a TOML file or .env line produces.
_VALID: list[tuple[object, EmailFormat]] = [
    ("html", EmailFormat.HTML),
    ("BOTH", EmailFormat.BOTH),
    (" Plain ", EmailFormat.PLAIN),
    ("plain\n", EmailFormat.PLAIN),
]

#: Values that name no format; each must mean HTML, never a refusal.
_INVALID: list[object] = ["pdf", "", " ", 1, 0, True, 1.5, ["html"], {"format": "html"}]


def _config(section: object) -> Config:
    return Config({"finanzonline": section}, {})


@pytest.mark.os_agnostic
class TestLoadEmailFormat:
    """The error-mail reader never raises and falls back to HTML."""

    def test_absent_key_means_html(self) -> None:
        assert load_email_format(_config(dict(_CREDENTIALS))) is EmailFormat.HTML

    def test_absent_section_means_html(self) -> None:
        assert load_email_format(Config({}, {})) is EmailFormat.HTML

    def test_section_that_is_not_a_table_means_html(self) -> None:
        assert load_email_format(_config("plain")) is EmailFormat.HTML

    @pytest.mark.parametrize("raw", _INVALID, ids=repr)
    def test_invalid_value_means_html(self, raw: object) -> None:
        assert load_email_format(_config({"email_format": raw})) is EmailFormat.HTML

    @pytest.mark.parametrize(("raw", "expected"), _VALID, ids=lambda value: repr(value))
    def test_valid_value_is_read(self, raw: object, expected: EmailFormat) -> None:
        assert load_email_format(_config({"email_format": raw})) is expected

    def test_other_keys_of_a_refused_section_do_not_hide_the_format(self) -> None:
        # The case the function exists for: the full section is refused (a bad
        # output_dir, no credentials), yet the error mail keeps the user's format.
        section = {"email_format": "plain", "output_dir": True, "session_timeout": "slow"}
        with pytest.raises(ConfigurationError):
            load_finanzonline_config(_config(section))

        assert load_email_format(_config(section)) is EmailFormat.PLAIN


@pytest.mark.os_agnostic
class TestFullSectionLoad:
    """The full section reads email_format through the same rule."""

    @pytest.mark.parametrize("raw", _INVALID, ids=repr)
    def test_invalid_value_falls_back_to_html(self, raw: object) -> None:
        loaded = load_finanzonline_config(_config({**_CREDENTIALS, "email_format": raw}))

        assert loaded.email_format is EmailFormat.HTML

    def test_invalid_value_adds_nothing_to_another_refusal(self) -> None:
        with pytest.raises(ConfigurationError) as caught:
            load_finanzonline_config(_config({**_CREDENTIALS, "email_format": "pdf", "output_dir": ["x"]}))

        assert str(caught.value) == "Invalid FinanzOnline configuration: finanzonline.output_dir: must be a directory path given as text, got list"

    @pytest.mark.parametrize("raw", [raw for raw, _ in _VALID] + _INVALID, ids=repr)
    def test_both_readers_agree(self, raw: object) -> None:
        config = _config({**_CREDENTIALS, "email_format": raw})

        assert load_finanzonline_config(config).email_format is load_email_format(config)
