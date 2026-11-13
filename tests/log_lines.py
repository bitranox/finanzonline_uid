"""The console log lines lib_log_rich adds to stderr, and how to make them recognisable.

Tests that compare a command's stderr across runs drop these lines first: lib_log_rich writes them
from a queue worker, so where they land among the command's own lines, and their timestamp, differ
from run to run. ``LOG_LINE`` matches the ``short_loc`` console layout. That layout is the default
everywhere except Windows, whose default ``short_loc_icon`` puts an icon where the bracketed level
is, so the rootdir conftest sets ``PINNED_CONSOLE_LAYOUT`` for every test, and a test that builds a
child process's environment from scratch adds it again. Imported by bare name, like
``layer_roots``: ``pythonpath`` puts ``tests/`` on ``sys.path``.
"""

from __future__ import annotations

import re

__all__ = ["LOG_LINE", "PINNED_CONSOLE_LAYOUT"]

#: One console log line in the ``short_loc`` layout: ``[HH:MM:SS][LEVEL]: message``.
LOG_LINE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]\[[A-Z]+\]: .*\n", re.MULTILINE)

#: The environment entry that makes lib_log_rich use the layout ``LOG_LINE`` matches on every OS.
PINNED_CONSOLE_LAYOUT: dict[str, str] = {"LOG_CONSOLE_FORMAT_PRESET": "short_loc"}
