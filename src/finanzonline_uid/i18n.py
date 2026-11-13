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

The language arrives as a :class:`~finanzonline_uid.enums.Language` member:
reading and validating the configured text happens at the configuration
boundary, :func:`finanzonline_uid.config.load_app_config`. An unsupported
language falls back to English there without a warning, because the CLI reads
``[app]`` before logging is initialised.

Examples
--------
>>> setup_locale(Language.DE)
>>> _("UID is valid") == "UID ist g\u00fcltig"
True
>>> setup_locale()
"""

from __future__ import annotations

import gettext
import logging
from pathlib import Path
from typing import Final

from .enums import Language

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES: Final[tuple[Language, ...]] = tuple(Language)
DEFAULT_LANGUAGE: Final = Language.EN

# Module-level state for current translation
_current_translation: gettext.GNUTranslations | gettext.NullTranslations | None = None
_current_language: Language = DEFAULT_LANGUAGE


def _get_locale_dir() -> Path:
    """Return the path to the locales directory."""
    return Path(__file__).parent / "locales"


def setup_locale(language: Language = DEFAULT_LANGUAGE) -> None:
    """Initialize gettext with the specified language.

    Args:
        language: Interface language. Defaults to English. If its
            translation files are missing, falls back to English.

    Side Effects:
        Sets the module-level translation object used by _() function.
        Logs a debug message indicating the active language.
    """
    global _current_translation, _current_language

    _current_language = language

    # English is the source language, no translation needed
    if language == Language.EN:
        _current_translation = gettext.NullTranslations()
        logger.debug("Locale initialized: en (source language)")
        return

    # Try to load translation for the requested language
    locale_dir = _get_locale_dir()
    try:
        _current_translation = gettext.translation(
            "messages",
            localedir=str(locale_dir),
            languages=[language.value],
        )
        logger.debug("Locale initialized: %s", language.value)
    except FileNotFoundError:
        logger.warning(
            "Translation files not found for '%s', falling back to '%s'",
            language.value,
            DEFAULT_LANGUAGE.value,
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
        >>> from finanzonline_uid.i18n import setup_locale, _
        >>> setup_locale(Language.EN)
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


def get_current_language() -> Language:
    """Return the currently active language.

    Returns:
        The active language; English after a fallback.
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
