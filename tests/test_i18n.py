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

from collections.abc import Generator

import pytest

from uid_check_austria.i18n import (
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
        assert DEFAULT_LANGUAGE == "en"

    def test_supported_languages(self) -> None:
        """All expected languages should be supported."""
        expected = ("en", "de", "es", "fr", "ru")
        assert SUPPORTED_LANGUAGES == expected

    def test_setup_english(self) -> None:
        """Setting up English locale should work."""
        setup_locale("en")
        assert get_current_language() == "en"

    def test_setup_german(self) -> None:
        """Setting up German locale should work."""
        setup_locale("de")
        assert get_current_language() == "de"

    def test_setup_spanish(self) -> None:
        """Setting up Spanish locale should work."""
        setup_locale("es")
        assert get_current_language() == "es"

    def test_setup_french(self) -> None:
        """Setting up French locale should work."""
        setup_locale("fr")
        assert get_current_language() == "fr"

    def test_setup_russian(self) -> None:
        """Setting up Russian locale should work."""
        setup_locale("ru")
        assert get_current_language() == "ru"

    def test_unsupported_language_falls_back_to_english(self) -> None:
        """Unsupported language should fall back to English."""
        setup_locale("xx")  # Nonexistent language
        assert get_current_language() == "en"

    def test_case_insensitive(self) -> None:
        """Language codes should be case-insensitive."""
        setup_locale("DE")
        assert get_current_language() == "de"

    def test_strips_whitespace(self) -> None:
        """Language codes should have whitespace stripped."""
        setup_locale("  de  ")
        assert get_current_language() == "de"


class TestTranslation:
    """Tests for _() translation function."""

    def test_english_returns_original(self) -> None:
        """English locale should return original strings."""
        setup_locale("en")
        assert _("UID is valid") == "UID is valid"

    def test_german_translation(self) -> None:
        """German locale should translate strings."""
        setup_locale("de")
        assert _("UID is valid") == "UID ist gültig"
        assert _("Yes") == "Ja"
        assert _("No") == "Nein"

    def test_spanish_translation(self) -> None:
        """Spanish locale should translate strings."""
        setup_locale("es")
        assert _("UID is valid") == "UID es válido"
        assert _("Yes") == "Sí"
        assert _("No") == "No"

    def test_french_translation(self) -> None:
        """French locale should translate strings."""
        setup_locale("fr")
        assert _("UID is valid") == "L'UID est valide"
        assert _("Yes") == "Oui"
        assert _("No") == "Non"

    def test_russian_translation(self) -> None:
        """Russian locale should translate strings."""
        setup_locale("ru")
        assert _("UID is valid") == "UID действителен"
        assert _("Yes") == "Да"
        assert _("No") == "Нет"

    def test_unknown_string_returns_original(self) -> None:
        """Unknown strings should return the original."""
        setup_locale("de")
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
        setup_locale("de")
        # N_() should NOT translate
        assert N_("UID is valid") == "UID is valid"
        # _() should translate
        assert _("UID is valid") == "UID ist gültig"


class TestReturnCodeTranslations:
    """Tests that return code messages are properly translated."""

    def test_return_code_info_translated(self) -> None:
        """Return code info should be translated at runtime."""
        from uid_check_austria.domain.return_codes import get_return_code_info

        # First in English
        setup_locale("en")
        info_en = get_return_code_info(0)
        assert info_en.meaning == "UID is valid"

        # Then in German
        setup_locale("de")
        info_de = get_return_code_info(0)
        assert info_de.meaning == "UID ist gültig"

        # And Spanish
        setup_locale("es")
        info_es = get_return_code_info(0)
        assert info_es.meaning == "UID es válido"


class TestFormatterTranslations:
    """Tests that formatter output is properly translated."""

    def test_status_labels_translated(self) -> None:
        """Status labels in formatters should be translated."""
        from datetime import datetime, timezone

        from uid_check_austria.adapters.output.formatters import format_human
        from uid_check_austria.domain.models import UidCheckResult

        result = UidCheckResult(
            uid="ATU12345678",
            return_code=0,
            message="Test",
            timestamp=datetime.now(timezone.utc),
        )

        # English
        setup_locale("en")
        output_en = format_human(result)
        assert "VALID" in output_en
        assert "UID Check Result" in output_en

        # German
        setup_locale("de")
        output_de = format_human(result)
        assert "GÜLTIG" in output_de
        assert "UID-Prüfungsergebnis" in output_de


@pytest.fixture(autouse=True)
def reset_locale() -> Generator[None, None, None]:
    """Reset locale to English after each test."""
    yield
    setup_locale("en")
