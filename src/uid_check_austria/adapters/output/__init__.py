"""Output formatters for CLI.

Purpose
-------
Format UID verification results for console output in human-readable
or JSON format.

Contents
--------
* :func:`.formatters.format_human` - Human-readable output
* :func:`.formatters.format_json` - JSON output

System Role
-----------
Adapters layer - transforms domain models into CLI output.
"""

from __future__ import annotations

from .formatters import format_human, format_json

__all__ = [
    "format_human",
    "format_json",
]
