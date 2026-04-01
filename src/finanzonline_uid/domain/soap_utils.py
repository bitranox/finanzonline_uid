"""SOAP response extraction utilities.

Purpose
-------
Provide reusable utilities for extracting data from SOAP response objects.

Contents
--------
* :func:`extract_string_attr` - Safely extract string attribute from SOAP response.
* :func:`is_html_response_error` - Detect HTML-instead-of-XML errors (maintenance pages).
* :func:`extract_html_maintenance_message` - Extract text from HTML maintenance page error.

System Role
-----------
Domain layer - pure utility functions with no I/O dependencies.
"""

from __future__ import annotations

import re
from typing import Any, cast


def extract_string_attr(response: Any, attr_name: str, default: str = "") -> str:
    """Extract a string attribute from a SOAP response object.

    Safely extracts an attribute from a SOAP response, handling:
    - Missing attributes (returns default)
    - None values (returns default)
    - Non-string values (casts to string)

    Args:
        response: SOAP response object with named attributes.
        attr_name: Attribute name to extract (e.g., 'adrz1', 'name').
        default: Default value if attribute is missing or None.

    Returns:
        Extracted string value, or default if not present.

    Examples:
        >>> class FakeResponse:
        ...     adrz1 = "Line 1"
        ...     adrz2 = None
        >>> r = FakeResponse()
        >>> extract_string_attr(r, "adrz1")
        'Line 1'
        >>> extract_string_attr(r, "adrz2")
        ''
        >>> extract_string_attr(r, "adrz3")
        ''
        >>> extract_string_attr(r, "adrz3", "N/A")
        'N/A'
    """
    value = getattr(response, attr_name, None)
    if value is None:
        return default
    return str(cast(str, value) or default)


# Patterns that indicate an HTML page was returned instead of SOAP XML.
# These appear in lxml XMLSyntaxError messages when parsing HTML as XML.
_HTML_TAG_PATTERNS: tuple[str, ...] = (
    "tag mismatch",
    "<html",
    "<head",
    "<body",
    "<!DOCTYPE",
)


def is_html_response_error(exc: Exception) -> bool:
    """Detect whether an exception indicates HTML was received instead of XML.

    When FinanzOnline returns an HTML maintenance page instead of a SOAP
    response, lxml raises an XMLSyntaxError with messages referencing
    HTML tags like <head>, <body>, or tag mismatches.

    Args:
        exc: The exception to check.

    Returns:
        True if the error message suggests HTML content instead of XML.

    Examples:
        >>> is_html_response_error(ValueError("Opening and ending tag mismatch: link line 10 and head"))
        True
        >>> is_html_response_error(ValueError("some other error"))
        False
    """
    error_text = str(exc).lower()
    return any(pattern.lower() in error_text for pattern in _HTML_TAG_PATTERNS)


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def extract_text_from_html_error(exc: Exception) -> str:
    """Extract readable text from an HTML-in-XML parsing error.

    Attempts to extract human-readable content from the HTML that caused
    the XML parsing error. Falls back to a generic maintenance message.

    Args:
        exc: The exception whose __cause__ or message may contain HTML.

    Returns:
        Extracted text content or generic maintenance message.

    Examples:
        >>> extract_text_from_html_error(ValueError("tag mismatch"))
        'FinanzOnline service returned a maintenance page instead of a SOAP response'
    """
    # Walk the exception chain looking for HTML content in the message
    current: BaseException | None = exc
    while current is not None:
        msg = str(current)
        if "<" in msg and ">" in msg:
            text = _HTML_TAG_RE.sub(" ", msg)
            text = _WHITESPACE_RE.sub(" ", text).strip()
            if len(text) > 20:
                return f"FinanzOnline maintenance: {text}"
        current = current.__cause__

    return "FinanzOnline service returned a maintenance page instead of a SOAP response"
