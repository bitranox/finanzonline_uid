"""Shared formatting utilities for adapters.

Purpose
-------
Provide reusable HTML formatting functions and templates used by both
output formatters and email notifications.

Contents
--------
* :mod:`.html_templates` - HTML constants and helper functions
* :mod:`.result_html` - Result HTML formatting

System Role
-----------
Adapters layer - shared formatting utilities to avoid circular imports.
"""

from __future__ import annotations

from .html_templates import (
    COLOR_GRAY,
    COLOR_GREEN,
    COLOR_RED,
    COLOR_YELLOW,
    HTML_BODY_STYLE,
    HTML_DOCTYPE,
    HTML_TABLE_STYLE,
    HTML_TD_STYLE,
    RATE_LIMITED_CODES,
    SERVICE_UNAVAILABLE_CODES,
)
from .result_html import format_result_html

__all__ = [
    # HTML Templates
    "HTML_DOCTYPE",
    "HTML_BODY_STYLE",
    "HTML_TABLE_STYLE",
    "HTML_TD_STYLE",
    "COLOR_GREEN",
    "COLOR_RED",
    "COLOR_YELLOW",
    "COLOR_GRAY",
    # Return code sets
    "SERVICE_UNAVAILABLE_CODES",
    "RATE_LIMITED_CODES",
    # Result Formatters
    "format_result_html",
]
