"""Internationalization support using gettext.

Purpose
-------
Provide multi-language support for user-facing messages using Python's
built-in gettext module. Supports English (default), German, Spanish,
French, and Russian.

Contents
--------
* :func:`setup_locale` - Initialize translations for a language
* :func:`_` - Translate a message string
* :func:`get_current_language` - Get the currently active language

System Role
-----------
Infrastructure module providing i18n capabilities. Called early in
application initialization to configure translations before any
user-facing output is generated.

Examples
--------
>>> setup_locale("de")
>>> _("UID is valid")
'UID ist gültig'
"""

from __future__ import annotations

import gettext
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Supported languages
SUPPORTED_LANGUAGES = ("en", "de", "es", "fr", "ru")
DEFAULT_LANGUAGE = "en"

# Module-level state for current translation
_current_translation: gettext.GNUTranslations | gettext.NullTranslations | None = None
_current_language: str = DEFAULT_LANGUAGE


def _get_locale_dir() -> Path:
    """Return the path to the locales directory."""
    return Path(__file__).parent / "locales"


def setup_locale(language: str = DEFAULT_LANGUAGE) -> None:
    """Initialize gettext with the specified language.

    Args:
        language: Language code (en, de, es, fr, ru). Defaults to English.
                  If the language is not supported or translation files
                  are missing, falls back to English.

    Side Effects:
        Sets the module-level translation object used by _() function.
        Logs a debug message indicating the active language.
    """
    global _current_translation, _current_language

    # Normalize and validate language
    lang = language.lower().strip()
    if lang not in SUPPORTED_LANGUAGES:
        logger.warning(
            "Unsupported language '%s', falling back to '%s'",
            language,
            DEFAULT_LANGUAGE,
        )
        lang = DEFAULT_LANGUAGE

    _current_language = lang

    # English is the source language, no translation needed
    if lang == "en":
        _current_translation = gettext.NullTranslations()
        logger.debug("Locale initialized: en (source language)")
        return

    # Try to load translation for the requested language
    locale_dir = _get_locale_dir()
    try:
        _current_translation = gettext.translation(
            "messages",
            localedir=str(locale_dir),
            languages=[lang],
        )
        logger.debug("Locale initialized: %s", lang)
    except FileNotFoundError:
        logger.warning(
            "Translation files not found for '%s', falling back to '%s'",
            lang,
            DEFAULT_LANGUAGE,
        )
        _current_translation = gettext.NullTranslations()
        _current_language = DEFAULT_LANGUAGE


def _(message: str) -> str:
    """Translate a message string.

    Args:
        message: The message to translate (in English).

    Returns:
        Translated message if available, otherwise the original message.

    Examples:
        >>> from uid_check_austria.i18n import setup_locale, _
        >>> setup_locale("en")
        >>> _("UID is valid")
        'UID is valid'
    """
    if _current_translation is None:
        return message
    return _current_translation.gettext(message)


def N_(message: str) -> str:
    """Mark a string for translation extraction without translating.

    Use this for strings that are defined at module level (like dictionary
    values) but translated at runtime via _().

    Args:
        message: The message to mark for extraction.

    Returns:
        The original message unchanged.

    Examples:
        >>> N_("UID is valid")
        'UID is valid'
    """
    return message


def get_current_language() -> str:
    """Return the currently active language code.

    Returns:
        The language code (en, de, es, fr, or ru).
    """
    return _current_language


__all__ = [
    "DEFAULT_LANGUAGE",
    "N_",
    "SUPPORTED_LANGUAGES",
    "_",
    "get_current_language",
    "setup_locale",
]
