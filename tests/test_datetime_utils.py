"""Tests for the shared wire timestamp type in _datetime_utils.

WireDatetime is the timestamp field of both on-disk JSON files (result cache
and rate-limit tracker), so its read and write forms are pinned here once.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import BaseModel, ValidationError

from finanzonline_uid._datetime_utils import WireDatetime, parse_wire_datetime


class _Stamped(BaseModel):
    at: WireDatetime


@pytest.mark.os_agnostic
class TestParseWireDatetime:
    """A stored timestamp reads back as an aware datetime."""

    def test_z_suffix_reads_as_utc(self) -> None:
        assert parse_wire_datetime("2025-01-15T10:30:00Z") == datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc)

    def test_naive_string_reads_as_utc(self) -> None:
        parsed = parse_wire_datetime("2025-01-15T10:30:00")
        assert parsed.tzinfo is timezone.utc

    def test_explicit_offset_is_kept(self) -> None:
        parsed = parse_wire_datetime("2025-01-15T10:30:00+02:00")
        assert parsed.utcoffset() == timedelta(hours=2)

    def test_naive_datetime_reads_as_utc(self) -> None:
        assert parse_wire_datetime(datetime(2025, 1, 15, 10, 30)).tzinfo is timezone.utc

    def test_non_string_is_refused_as_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            _Stamped.model_validate({"at": 12345})

    def test_non_iso_string_is_refused_as_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            _Stamped.model_validate({"at": "yesterday"})


@pytest.mark.os_agnostic
class TestWireDatetimeSerialization:
    """The written form is format_iso_datetime's, not Pydantic's."""

    def test_utc_dumps_with_z_suffix(self) -> None:
        stamped = _Stamped(at=datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc))
        assert stamped.model_dump(mode="json") == {"at": "2025-01-15T10:30:00Z"}

    def test_microseconds_appear_only_when_non_zero(self) -> None:
        stamped = _Stamped(at=datetime(2025, 1, 15, 10, 30, 0, 5, tzinfo=timezone.utc))
        assert stamped.model_dump(mode="json") == {"at": "2025-01-15T10:30:00.000005Z"}

    def test_round_trip_is_stable(self) -> None:
        wire = {"at": "2025-01-15T10:30:00Z"}
        assert _Stamped.model_validate(wire).model_dump(mode="json") == wire
