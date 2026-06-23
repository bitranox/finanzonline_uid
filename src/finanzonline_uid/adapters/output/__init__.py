"""Output formatters for CLI.

Purpose
-------
Format UID verification results for console output in human-readable,
JSON, or HTML format.

Contents
--------
* :func:`.formatters.format_human` - Human-readable result output
* :func:`.formatters.format_json` - JSON result output
* :func:`.formatters.format_html` - HTML document output
* :func:`.formatters.format_error_human` - Human-readable error output
* :func:`.formatters.format_error_json` - JSON error output

System Role
-----------
Adapters layer - transforms domain models into CLI output.
"""

from __future__ import annotations

from .formatters import format_error_human, format_error_json, format_html, format_human, format_json

__all__ = [
    "format_html",
    "format_human",
    "format_json",
    "format_error_human",
    "format_error_json",
]
