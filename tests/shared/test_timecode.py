from fractions import Fraction

import pytest

from markflow.shared.timecode import (
    TICKS_PER_SECOND, find_clocks, format_clock, parse_clock, parse_fps, seconds_to_ticks,
    snap_to_frame, ticks_per_frame, ticks_to_seconds,
)


@pytest.mark.parametrize("fps,ticks", [("60", 4_233_600_000), ("30", 8_467_200_000), ("29.97", 8_475_667_200),
                                       ("25", 10_160_640_000), ("59.94", 4_237_833_600)])
def test_ticks_per_frame_matches_premiere(fps, ticks):
    assert ticks_per_frame(parse_fps(fps)) == ticks


def test_parse_fps_forms():
    assert parse_fps("30000/1001") == Fraction(30000, 1001)
    assert parse_fps(29.97) == Fraction(30000, 1001)
    assert parse_fps("25") == 25


def test_seconds_ticks_round_trip():
    assert seconds_to_ticks(1) == TICKS_PER_SECOND
    assert ticks_to_seconds(seconds_to_ticks(12.5)) == 12.5


def test_snap_to_frame():
    tpf = ticks_per_frame(Fraction(25))
    assert snap_to_frame(tpf * 10 + tpf // 3, Fraction(25)) == tpf * 10
    assert snap_to_frame(tpf * 10 + tpf * 2 // 3, Fraction(25)) == tpf * 11


@pytest.mark.parametrize("text,seconds", [("1:15:13", 4513.0), ("32:40", 1960.0), ("0:26", 26.0)])
def test_parse_clock(text, seconds):
    assert parse_clock(text) == seconds


@pytest.mark.parametrize("bad", ["1", "1:75", "a:b"])
def test_parse_clock_rejects(bad):
    with pytest.raises(ValueError):
        parse_clock(bad)


def test_find_clocks_in_script_line():
    found = find_clocks("1:15:13 я подготовлюсь и разъебу тебя — 1:15:16")
    assert [s for _, _, s in found] == [4513.0, 4516.0]


def test_find_clocks_ignores_dates_and_numbers():
    assert find_clocks("в 2026-м году 30 лет") == []


def test_format_clock():
    assert format_clock(4513) == "1:15:13"
    assert format_clock(26) == "0:26"
