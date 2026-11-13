"""Tests for setting an unreadable state file aside before a rewrite."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from finanzonline_uid.adapters._state_file import set_aside_unreadable

_NOW = datetime(2026, 11, 13, 14, 43, 43, 123456, tzinfo=timezone.utc)


@pytest.mark.os_agnostic
class TestSetAsideUnreadable:
    """The bytes move to a sibling named for when they were found unreadable."""

    def test_the_name_carries_the_utc_time_and_the_bytes_are_kept(self, tmp_path: Path) -> None:
        state = tmp_path / "uid_cache.json"
        state.write_bytes(b"{ not json")
        vienna = timezone(timedelta(hours=1))

        aside = set_aside_unreadable(state, now=_NOW.astimezone(vienna))

        assert aside == tmp_path / "uid_cache.json.corrupt-2026-11-13T14-43-43.123456Z"
        assert aside.read_bytes() == b"{ not json"
        assert not state.exists()

    def test_names_sort_in_time_order(self, tmp_path: Path) -> None:
        state = tmp_path / "rate_limits.json"
        # Ascending times chosen to cross a year, a month and a day boundary, where a stamp
        # that does not lead with its most significant field sorts out of order.
        times = [
            datetime(2025, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
            datetime(2026, 10, 31, 9, 0, tzinfo=timezone.utc),
            _NOW - timedelta(microseconds=1),
            _NOW,
        ]
        names: list[str] = []
        for when in times:
            state.write_bytes(b"x")
            names.append(set_aside_unreadable(state, now=when).name)

        assert names == sorted(names)

    def test_a_clash_in_the_same_microsecond_keeps_both_copies(self, tmp_path: Path) -> None:
        state = tmp_path / "uid_cache.json"
        state.write_bytes(b"first")
        first = set_aside_unreadable(state, now=_NOW)
        state.write_bytes(b"second")

        second = set_aside_unreadable(state, now=_NOW)

        assert second == first.with_name(f"{first.name}-1")
        assert (first.read_bytes(), second.read_bytes()) == (b"first", b"second")
