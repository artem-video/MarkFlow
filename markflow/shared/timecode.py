"""Premiere time units and human timecodes. Pure functions, no I/O."""

from __future__ import annotations

import re
from fractions import Fraction

TICKS_PER_SECOND = 254_016_000_000

# Frame rates seen in real sources (CLAUDE.md: never assume one fps).
KNOWN_FPS: dict[str, Fraction] = {
    "23.976": Fraction(24000, 1001),
    "24": Fraction(24),
    "25": Fraction(25),
    "29.97": Fraction(30000, 1001),
    "30": Fraction(30),
    "50": Fraction(50),
    "59.94": Fraction(60000, 1001),
    "60": Fraction(60),
}


def parse_fps(value: str | float | Fraction) -> Fraction:
    """'29.97', '30000/1001', 25, 59.94 -> exact Fraction."""
    if isinstance(value, Fraction):
        return value
    text = str(value).strip()
    if "/" in text:
        num, den = text.split("/", 1)
        return Fraction(int(num), int(den))
    for key, fps in KNOWN_FPS.items():
        if abs(float(text) - float(fps)) < 0.005:
            return fps
    return Fraction(text)


def ticks_per_frame(fps: Fraction) -> int:
    ticks = Fraction(TICKS_PER_SECOND) / fps
    if ticks.denominator != 1:
        raise ValueError(f"fps {fps} does not give a whole number of ticks per frame")
    return int(ticks)


def seconds_to_ticks(seconds: float | Fraction) -> int:
    return round(Fraction(seconds) * TICKS_PER_SECOND)


def ticks_to_seconds(ticks: int) -> float:
    return ticks / TICKS_PER_SECOND


def snap_to_frame(ticks: int, fps: Fraction) -> int:
    """Round a tick position to the nearest frame boundary of the given rate."""
    tpf = ticks_per_frame(fps)
    return round(ticks / tpf) * tpf


_TC_RE = re.compile(r"(?<![\d:])(\d{1,2}(?::\d{2}){1,2})(?![\d:])")


def parse_clock(text: str) -> float:
    """'1:15:13' -> 4513.0, '32:40' -> 1960.0 (no frames; script/live timecodes)."""
    parts = [int(p) for p in text.strip().split(":")]
    if not 2 <= len(parts) <= 3 or any(p < 0 for p in parts) or any(p >= 60 for p in parts[1:]):
        raise ValueError(f"not a clock timecode: {text!r}")
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return float(seconds)


def find_clocks(text: str) -> list[tuple[int, int, float]]:
    """All clock timecodes in free text as (start, end, seconds)."""
    found = []
    for m in _TC_RE.finditer(text):
        try:
            found.append((m.start(1), m.end(1), parse_clock(m.group(1))))
        except ValueError:
            continue
    return found


def format_clock(seconds: float) -> str:
    total = int(round(seconds))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
