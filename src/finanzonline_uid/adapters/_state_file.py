"""Keep an unreadable state file aside before a write replaces it.

The result cache and the rate-limit tracker each keep one JSON file that every
write reads, updates and rewrites. When that file is not valid JSON the write
cannot merge into it, and failing the write would fail a UID check that
FinanzOnline already answered. Overwriting it would destroy whatever the bytes
were. So the write moves the bytes to a sibling file whose name says they were
unreadable and when, and then starts the file afresh.

Contents:
    * :func:`set_aside_unreadable` - move the file aside and log one warning

System Role:
    Shared by the cache and rate-limit adapters; both call it while holding the
    file's own lock, so no other writer can read or replace the file between
    the failed parse and the move.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["set_aside_unreadable"]

logger = logging.getLogger(__name__)

# Hyphens instead of colons: Windows refuses ":" in a file name. Fixed width
# and most significant field first, so the names sort in time order.
_STAMP_FORMAT = "%Y-%m-%dT%H-%M-%S.%fZ"


def _aside_path(path: Path, now: datetime) -> Path:
    """Return a free sibling name that marks the file unreadable at ``now`` (UTC).

    The stamp has microseconds, so a clash means two set-asides of the same
    file in the same microsecond; a counter then keeps the older copy intact.

    Args:
        path: The unreadable file.
        now: When it was found unreadable (any timezone; written as UTC).

    Returns:
        A path in the same directory that does not exist yet.

    Examples:
        >>> stamp = datetime(2026, 11, 13, 14, 43, 43, 123456, tzinfo=timezone.utc)
        >>> _aside_path(Path("/opt/state/uid_cache.json"), stamp).name
        'uid_cache.json.corrupt-2026-11-13T14-43-43.123456Z'
    """
    base = f"{path.name}.corrupt-{now.astimezone(timezone.utc).strftime(_STAMP_FORMAT)}"
    candidate = path.with_name(base)
    counter = 1
    while candidate.exists():
        candidate = path.with_name(f"{base}-{counter}")
        counter += 1
    return candidate


def set_aside_unreadable(path: Path, *, now: datetime) -> Path:
    """Move an unreadable state file to a sibling name and log one warning.

    Call it with the file's lock held. A rename within one directory keeps the
    bytes exactly and needs no copy; the caller then writes a fresh file at
    ``path``.

    Args:
        path: The state file whose content could not be parsed.
        now: When it was found unreadable; becomes part of the new name.

    Returns:
        Where the original bytes now are.

    Raises:
        OSError: The rename failed; the file stays where it was.
    """
    aside = _aside_path(path, now)
    path.replace(aside)
    logger.warning("%s is not valid JSON; kept it as %s and started a new file", path, aside)
    return aside
