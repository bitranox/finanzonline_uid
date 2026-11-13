"""Shared datetime utilities for internal use.

This module provides common datetime parsing and formatting functions
used across multiple adapters to avoid code duplication.

Contents:
    * :func:`parse_iso_datetime` - Parse ISO format string to datetime
    * :func:`format_iso_datetime` - Format datetime to ISO string with Z suffix
    * :func:`format_local_time` - Format datetime as local time string
    * :func:`parse_wire_datetime` - Parse a stored timestamp, naive read as UTC
    * :data:`WireDatetime` - Pydantic field type for a timestamp in an on-disk JSON file
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer
from pydantic_core import PydanticCustomError

__all__ = [
    "WireDatetime",
    "format_iso_datetime",
    "format_local_time",
    "parse_iso_datetime",
    "parse_wire_datetime",
]


def parse_iso_datetime(iso_str: str) -> datetime:
    """Parse ISO format datetime string to datetime object.

    Args:
        iso_str: ISO format datetime string (e.g., "2025-01-15T10:30:00Z").

    Returns:
        Timezone-aware datetime object.
    """
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


def format_iso_datetime(dt: datetime) -> str:
    """Format datetime to ISO string with Z suffix for UTC.

    Args:
        dt: Datetime object (naive or timezone-aware).

    Returns:
        ISO format string with Z suffix for UTC times.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def format_local_time(dt: datetime) -> str:
    """Format datetime as local time string.

    Args:
        dt: Datetime object (can be UTC or timezone-aware).

    Returns:
        Formatted string in local time: "YYYY-MM-DD HH:MM:SS"
    """
    local_dt = dt.astimezone()  # Convert to local timezone
    return local_dt.strftime("%Y-%m-%d %H:%M:%S")


def parse_wire_datetime(value: object) -> datetime:
    """Parse a stored timestamp the way installed versions do.

    parse_iso_datetime is the parser installed versions use, so the set of
    accepted strings stays the same. A string without an offset is read as
    UTC because format_iso_datetime writes naive datetimes as UTC; comparing
    it unconverted with an aware clock reading would raise TypeError.

    Args:
        value: Raw JSON value, or a datetime when a model is built in code.

    Returns:
        Timezone-aware datetime.

    Raises:
        PydanticCustomError: The value is neither a string nor a datetime.
        ValueError: The string is not ISO 8601 (from parse_iso_datetime).

    Examples:
        >>> parse_wire_datetime("2025-01-15T10:30:00Z").isoformat()
        '2025-01-15T10:30:00+00:00'
        >>> parse_wire_datetime("2025-01-15T10:30:00").isoformat()
        '2025-01-15T10:30:00+00:00'
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = parse_iso_datetime(value)
    else:
        # PydanticCustomError, unlike a TypeError, becomes a ValidationError
        # and so lets the caller skip the entry instead of escaping the validator.
        raise PydanticCustomError("wire_datetime_type", "expected an ISO 8601 timestamp string")
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


# Serialized through format_iso_datetime, not Pydantic's own datetime form:
# installed versions wrote "...Z" with microseconds only when non-zero, and
# that exact string is part of the on-disk wire of the cache and rate-limit files.
WireDatetime = Annotated[
    datetime,
    BeforeValidator(parse_wire_datetime),
    PlainSerializer(format_iso_datetime, return_type=str),
]
"""Pydantic field type for a timestamp stored in an on-disk JSON file.

Reads any string parse_iso_datetime accepts (naive read as UTC) and writes
the format_iso_datetime form ("...Z").
"""
