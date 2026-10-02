"""Script comments -> timeline (PLAN 5.1). Pure: comment text in, subtitles out.

A comment is an instruction to the editor and goes on the timeline as a subtitle on a track of its own, word for
word as in the script ('ВИДЕО: <ссылка>' / '47:48 Можно ускорить'): the editor reads it, nothing is paraphrased.
A comment addressed to a colleague ('@name@mail.com Лех, тут лайв нужен') is not about the edit and is ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from markflow.shared.timecode import TICKS_PER_SECOND

SUBTITLE_DEFAULT_S = 4.0
SUBTITLE_MIN_S = 2.0
SUBTITLE_MAX_S = 6.0

_ADDRESSED = re.compile(r"@[\w.+-]+@[\w-]+\.\w+|(?<![\w/])@\w{3,}")  # an e-mail or a @mention


def is_for_editor(text: str) -> bool:
    """False for comments that talk to a colleague instead of the edit."""
    return bool(text.strip()) and not _ADDRESSED.search(text)


def subtitle_text(text: str) -> str:
    """The comment as written, lines kept, blank lines and edge spaces dropped."""
    return "\n".join(line.strip() for line in text.replace("\r", "").split("\n") if line.strip())


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
