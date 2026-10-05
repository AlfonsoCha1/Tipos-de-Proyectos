"""Pruebas de fechas y zonas horarias."""

from datetime import datetime, timedelta, timezone

import pytest

from login_counter.timeutils import (
    TimestampError,
    TimezoneError,
    format_duration,
    format_timestamp,
    load_timezone,
    parse_iso_timestamp,
)

MEXICO = load_timezone("America/Mexico_City")


def test_load_timezone_accepts_utc_offsets_and_iana_names():
    assert load_timezone("utc") is timezone.utc
    assert load_timezone("-06:00").utcoffset(None) == timedelta(hours=-6)
    assert load_timezone("+0530").utcoffset(None) == timedelta(hours=5, minutes=30)
    assert MEXICO is not None


@pytest.mark.parametrize("name", ["Marte/Olympus", "", "../etc/passwd", "+25:00"])
def test_load_timezone_rejects_invalid_names(name):
    with pytest.raises(TimezoneError):
        load_timezone(name)


def test_offsets_are_normalized_to_utc():
    assert parse_iso_timestamp("2026-09-14T08:10:02-06:00", timezone.utc) == datetime(
        2026, 9, 14, 14, 10, 2, tzinfo=timezone.utc
    )
    assert parse_iso_timestamp("2026-09-14T14:10:02Z", MEXICO) == datetime(
        2026, 9, 14, 14, 10, 2, tzinfo=timezone.utc
    )


def test_naive_timestamp_uses_default_timezone():
    # 10:00 en Ciudad de México (UTC-6 desde 2022, sin horario de verano) = 16:00 UTC.
    assert parse_iso_timestamp("2026-09-14T10:00:00", MEXICO).hour == 16
    assert parse_iso_timestamp("2026-09-14T10:00:00", timezone.utc).hour == 10


def test_fractional_seconds_are_accepted():
    parsed = parse_iso_timestamp("2026-09-14T08:15:02.5-06:00", timezone.utc)
    assert parsed.microsecond == 500_000


@pytest.mark.parametrize(
    "text",
    ["2026-09-31T10:00:00Z", "14/09/2026 10:00", "2026-09-14", "20260914T100000Z", "ayer"],
)
def test_invalid_timestamps_raise_clear_error(text):
    with pytest.raises(TimestampError):
        parse_iso_timestamp(text, timezone.utc)


def test_format_helpers():
    value = datetime(2026, 9, 14, 14, 10, 2, tzinfo=timezone.utc)
    assert format_timestamp(value, MEXICO) == "2026-09-14 08:10:02-06:00"
    assert format_duration(timedelta(minutes=3, seconds=28)) == "3 min 28 s"
    assert format_duration(timedelta(seconds=9)) == "9 s"
    assert format_duration(timedelta(hours=1, seconds=5)) == "1 h 0 min 5 s"
