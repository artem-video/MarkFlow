"""Script comments -> timeline (PLAN 5.1). Pure: comment text in, a decision out.

A comment is an instruction to the editor. Ordinary ones ('показать', 'выделить', 'файл 9012') become a ranged
marker at the phrase they are attached to. Non-standard ones (a title, a footnote, an effect, a sound, a layout
wish) are easy to miss in a marker, so they are also shown as a subtitle on a track of their own.
Links and timecodes are the lives' business (PLAN 4); they never reach the subtitle text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from markflow.shared.text_norm import normalize, without_links
from markflow.shared.timecode import TICKS_PER_SECOND, find_clocks

SUBTITLE_MAX_CHARS = 140
SUBTITLE_DEFAULT_S = 4.0
SUBTITLE_MIN_S = 2.0
SUBTITLE_MAX_S = 6.0

# stems of the normalised text: something the editor must build, not just find and place
_NONSTANDARD = re.compile(
    r"\b(титр\w*|сноск\w*|плашк\w*|эффект\w*|фишай\w*|растян\w*|растяг\w*|зум\w*|увелич\w*|замедл\w*|шрифт\w*|"
    r"анимаци\w*|размыт\w*|звук\w*|музык\w*|смех\w*|мемн\w*|смешн\w*|комичн\w*|шутк\w*|сбоку)\b")


_URL_END = re.compile(r"(https?://[^\s\u0400-\u04ff]+)")


def instruction_text(text: str) -> str:
    """The comment without links and timecodes, on one line."""
    text = without_links(_URL_END.sub(r"\1 ", text))  # Docs glues the text to the end of a link
    for a, b, _ in reversed(find_clocks(text)):
        text = text[:a] + " " + text[b:]
    return re.sub(r"\s+", " ", text).strip(" :;,.-—")


def is_nonstandard(text: str) -> bool:
    return bool(_NONSTANDARD.search(normalize(instruction_text(text))))


def subtitle_text(text: str) -> str:
    """One readable line: the instruction itself, cut at a word boundary."""
    line = instruction_text(text)
    if len(line) <= SUBTITLE_MAX_CHARS:
        return line
    return line[:SUBTITLE_MAX_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:—-") + "…"


@dataclass(frozen=True)
class Cue:
    """A subtitle before placing: times in ticks."""

    start: int
    duration: int
    text: str
    note: str = ""
    script_ref: str | None = None


def cue_duration(span: int, frame: int) -> int:
    """How long a subtitle stays: as long as the phrase it is attached to, but readable (2–6 s; 4 s when unknown)."""
    seconds = SUBTITLE_DEFAULT_S if span <= 0 else min(SUBTITLE_MAX_S, max(SUBTITLE_MIN_S, span / TICKS_PER_SECOND))
    return max(frame, round(seconds * TICKS_PER_SECOND / frame) * frame)


def place_cues(cues: list[Cue], frame: int) -> list[Cue]:
    """No two subtitles overlap on one track: an earlier one is cut where the next starts; cues that start at
    the same moment follow each other."""
    out: list[Cue] = []
    for cue in sorted(cues, key=lambda c: c.start):
        if out and out[-1].start + out[-1].duration > cue.start:
            prev = out[-1]
            if cue.start - prev.start >= frame:
                out[-1] = replace(prev, duration=cue.start - prev.start)
            else:
                cue = replace(cue, start=prev.start + prev.duration)
        out.append(cue)
    return out
