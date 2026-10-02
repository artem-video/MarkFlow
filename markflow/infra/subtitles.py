"""Subtitles of the plan as an .srt file: Premiere imports it onto a caption track of its own (PLAN 5.1)."""

from __future__ import annotations

from pathlib import Path

from markflow.domain.edit_plan import EditPlan
from markflow.shared.timecode import TICKS_PER_SECOND


def _stamp(ticks: int) -> str:
    ms = round(ticks * 1000 / TICKS_PER_SECOND)
    h, rest = divmod(ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, ms = divmod(rest, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt_text(plan: EditPlan) -> str:
    cues = []
    for i, u in enumerate(sorted(plan.subtitles, key=lambda u: u.start), 1):
        cues.append(f"{i}\n{_stamp(u.start)} --> {_stamp(u.start + u.duration)}\n{u.text}\n")
    return "\n".join(cues)


def write_srt(plan: EditPlan, path: Path) -> Path:
    path.write_text(srt_text(plan), encoding="utf-8")
    return path
