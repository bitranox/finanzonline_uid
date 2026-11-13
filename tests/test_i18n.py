"""Tests for internationalization (i18n) module.

Purpose
-------
Verify that the i18n system correctly initializes and translates strings
for all supported languages.

Contents
--------
* Test locale setup for all supported languages
* Test translation function behavior
* Test fallback to English for unsupported languages
* Test N_() marker function
"""

from __future__ import annotations

import ast
import gettext
from collections.abc import Generator
from pathlib import Path

import pytest

from finanzonline_uid import i18n as i18n_module
from finanzonline_uid.config import AppSection
from finanzonline_uid.enums import Language
from finanzonline_uid.i18n import (
    DEFAULT_LANGUAGE,
    N_,
    SUPPORTED_LANGUAGES,
    _,
    get_current_language,
    setup_locale,
)


class TestSetupLocale:
    """Tests for setup_locale function."""

    def test_default_language_is_english(self) -> None:
        """Default language should be English."""
        assert DEFAULT_LANGUAGE == Language.EN

    def test_supported_languages(self) -> None:
        """All expected languages should be supported, in this order."""
        assert [language.value for language in SUPPORTED_LANGUAGES] == ["en", "de", "es", "fr", "ru"]

    @pytest.mark.parametrize("language", list(Language))
    def test_setup_language(self, language: Language) -> None:
        """Every supported language ships its catalog and becomes the current one."""
        setup_locale(language)
        assert get_current_language() == language

    def test_setup_without_argument_is_english(self) -> None:
        """Calling setup_locale() without a language selects English."""
        setup_locale(Language.DE)
        setup_locale()
        assert get_current_language() == Language.EN


class TestLanguageFromConfiguration:
    """The configured text becomes a Language at the configuration boundary."""

    def test_unsupported_language_falls_back_to_english(self) -> None:
        """An unsupported language code selects English."""
        assert AppSection.model_validate({"language": "xx"}).language == Language.EN

    def test_case_insensitive(self) -> None:
        """Language codes are case-insensitive."""
        assert AppSection.model_validate({"language": "DE"}).language == Language.DE

    def test_strips_whitespace(self) -> None:
        """Language codes have surrounding whitespace stripped."""
        assert AppSection.model_validate({"language": "  de  "}).language == Language.DE


class TestTranslation:
    """Tests for _() translation function."""

    def test_english_returns_original(self) -> None:
        """English locale should return original strings."""
        setup_locale(Language.EN)
        assert _("UID is valid") == "UID is valid"

    def test_german_translation(self) -> None:
        """German locale should translate strings."""
        setup_locale(Language.DE)
        assert _("UID is valid") == "UID ist gültig"
        assert _("Yes") == "Ja"
        assert _("No") == "Nein"

    def test_spanish_translation(self) -> None:
        """Spanish locale should translate strings."""
        setup_locale(Language.ES)
        assert _("UID is valid") == "UID es válido"
        assert _("Yes") == "Sí"
        assert _("No") == "No"

    def test_french_translation(self) -> None:
        """French locale should translate strings."""
        setup_locale(Language.FR)
        assert _("UID is valid") == "L'UID est valide"
        assert _("Yes") == "Oui"
        assert _("No") == "Non"

    def test_russian_translation(self) -> None:
        """Russian locale should translate strings."""
        setup_locale(Language.RU)
        assert _("UID is valid") == "UID действителен"
        assert _("Yes") == "Да"
        assert _("No") == "Нет"

    def test_unknown_string_returns_original(self) -> None:
        """Unknown strings should return the original."""
        setup_locale(Language.DE)
        unknown = "This string does not exist in translations"
        assert _(unknown) == unknown


class TestMarkerFunction:
    """Tests for N_() marker function."""

    def test_n_returns_original(self) -> None:
        """N_() should return the original string unchanged."""
        test_string = "Test string for marking"
        assert N_(test_string) == test_string

    def test_n_does_not_translate(self) -> None:
        """N_() should not translate, just mark for extraction."""
        setup_locale(Language.DE)
        # N_() should NOT translate
        assert N_("UID is valid") == "UID is valid"
        # _() should translate
        assert _("UID is valid") == "UID ist gültig"


class TestReturnCodeTranslations:
    """Tests that return code messages are properly translated."""

    def test_return_code_info_translated(self) -> None:
        """Return code info should be translated at runtime."""
        from finanzonline_uid.domain.return_codes import get_return_code_info

        # First in English
        setup_locale(Language.EN)
        info_en = get_return_code_info(0)
        assert info_en.meaning == "UID is valid"

        # Then in German
        setup_locale(Language.DE)
        info_de = get_return_code_info(0)
        assert info_de.meaning == "UID ist gültig"

        # And Spanish
        setup_locale(Language.ES)
        info_es = get_return_code_info(0)
        assert info_es.meaning == "UID es válido"


class TestFormatterTranslations:
    """Tests that formatter output is properly translated."""

    def test_status_labels_translated(self) -> None:
        """Status labels in formatters should be translated."""
        from datetime import datetime, timezone

        from finanzonline_uid.adapters.output.formatters import format_human
        from finanzonline_uid.domain.models import UidCheckResult

        result = UidCheckResult(
            uid="ATU12345678",
            return_code=0,
            message="Test",
            timestamp=datetime.now(timezone.utc),
        )

        # English
        setup_locale(Language.EN)
        output_en = format_human(result)
        assert "VALID" in output_en
        assert "UID Check Result" in output_en

        # German
        setup_locale(Language.DE)
        output_de = format_human(result)
        assert "GÜLTIG" in output_de
        assert "UID-Prüfungsergebnis" in output_de

    def test_result_status_labels_translated(self) -> None:
        """The status badge of the email bodies is translated per ResultStatus."""
        from datetime import datetime, timezone

        from finanzonline_uid.adapters.formatting.html_templates import ResultStatus, classify_result, result_status_label
        from finanzonline_uid.adapters.notification.plain_formatter import format_result_plain
        from finanzonline_uid.domain.models import UidCheckResult

        setup_locale(Language.DE)
        assert result_status_label(ResultStatus.VALID) == "G\u00dcLTIG"
        assert result_status_label(classify_result(1513)) == "RATENLIMIT"
        result = UidCheckResult(uid="ATU1", return_code=1, message="m", timestamp=datetime.now(timezone.utc))
        assert result_status_label(ResultStatus.INVALID) in format_result_plain(result)


@pytest.fixture(autouse=True)
def reset_locale() -> Generator[None, None, None]:
    """Reset locale to English after each test."""
    yield
    setup_locale(Language.EN)


def _po_entries(po_path: Path) -> dict[str, str]:
    """Return msgid -> msgstr of a .po file (single and continued string lines)."""
    entries: dict[str, str] = {}
    key: str | None = None
    current: list[str] = []
    msgid = ""

    def _close() -> None:
        if key == "msgstr" and msgid:
            entries[msgid] = "".join(current)

    for raw in po_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith(("msgid ", "msgstr ")):
            if key == "msgid":
                msgid = "".join(current)
            _close()
            key, _sep, literal = line.partition(" ")
            current = [ast.literal_eval(literal)]
        elif line.startswith('"') and key is not None:
            current.append(ast.literal_eval(line))
        else:
            if key == "msgid":
                msgid = "".join(current)
            _close()
            key = None
    if key == "msgid":
        msgid = "".join(current)
    _close()
    return entries


@pytest.mark.parametrize("language", [lang for lang in SUPPORTED_LANGUAGES if lang != DEFAULT_LANGUAGE])
def test_compiled_catalog_carries_every_po_translation(language: Language) -> None:
    """The shipped .mo must hold every translation its .po declares.

    Measured: four retry-mode strings were translated in the .po files and never
    compiled, so those lines stayed English in every non-English locale.
    """
    locale_dir = Path(i18n_module.__file__).parent / "locales" / language.value / "LC_MESSAGES"
    entries = _po_entries(locale_dir / "messages.po")
    with (locale_dir / "messages.mo").open("rb") as mo_file:
        catalog = gettext.GNUTranslations(mo_file)

    missing = sorted(msgid for msgid, msgstr in entries.items() if msgstr and catalog.gettext(msgid) != msgstr)

    assert len(entries) > 100, "the .po parser read almost nothing; the check would pass vacuously"
    assert missing == []
