"""Source map «as on set» (stage 2.2). Pure.

- recording order comes from the file names (camera and recorder patterns) or the container date;
- an audio-only recording is voice-over;
- the first shoot day is the main shoot; a later recording that repeats script text already recorded
  is a retake (it wins), one that brings new text is a pickup (добор);
- which source every script sentence finally comes from, and where a later source overrode an earlier one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime

from markflow.domain.align import Alignment
from markflow.domain.edit_plan import SourceKind

_PATTERNS = (
    (re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})[_-]?B?(\d{3,4})?"), "ymd"),   # 20260828_B0001
    (re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?!\d)"), "ymdhm"),  # Keyed-Video_2608311425
)


def recorded_at_from_name(name: str) -> tuple[datetime, int] | None:
    """(datetime, clip number) from a camera/recorder file name, or None."""
    for rx, kind in _PATTERNS:
        for m in rx.finditer(name):
            try:
                if kind == "ymd":
                    number = int(m.group(4)) if m.group(4) else 0
                    return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))), number
                y, mo, d, h, mi = (int(g) for g in m.groups())
                return datetime(2000 + y, mo, d, h, mi), 0
            except ValueError:
                continue
    return None


@dataclass(frozen=True)
class SourceMeta:
    id: str
    path: str
    duration: float
    fps: str | None                 # None for audio-only
    audio_channels: int
    width: int | None = None
    height: int | None = None
    recorded_at: datetime | None = None
    number: int = 0
    kind: SourceKind | None = None  # decided by triage unless given

    @property
    def audio_only(self) -> bool:
        return self.fps is None


def with_recording_time(meta: SourceMeta, container_date: datetime | None = None) -> SourceMeta:
    from_name = recorded_at_from_name(meta.path.replace("\\", "/").split("/")[-1])
    if from_name:
        return replace(meta, recorded_at=from_name[0], number=from_name[1])
    return replace(meta, recorded_at=container_date)


def recording_order(metas: list[SourceMeta]) -> list[SourceMeta]:
    """Oldest first; unknown dates last, then by name."""
    return sorted(metas, key=lambda m: (m.recorded_at is None, m.recorded_at or datetime.max, m.number, m.path))


@dataclass(frozen=True)
class SourceReport:
    meta: SourceMeta
    kind: SourceKind
    units_heard: int        # script sentences with at least one take here
    units_chosen: int       # sentences finally taken from here
    overrides: int          # sentences where this source beat an earlier one


@dataclass(frozen=True)
class SourceMap:
    sources: tuple[SourceReport, ...]
    unit_source: dict[str, str]          # unit id -> source id it is taken from
    overridden: tuple[tuple[str, str, str], ...]  # (unit id, earlier source, later source that wins)
    missing_units: tuple[str, ...]


def classify_sources(ordered: list[SourceMeta], alignment: Alignment) -> SourceMap:
    heard: dict[str, set[str]] = {m.id: set() for m in ordered}
    for sid, occs in alignment.occurrences.items():
        heard.setdefault(sid, set()).update(o.unit_id for o in occs)
    chosen: dict[str, str] = {}
    overridden = []
    for c in alignment.choices:
        if c.chosen is None:
            continue
        chosen[c.unit.id] = c.chosen.source_id
        earlier = [o.source_id for o in c.takes if o.sort_key < c.chosen.sort_key and o.source_id != c.chosen.source_id]
        if earlier:
            overridden.append((c.unit.id, earlier[-1], c.chosen.source_id))
    video = [m for m in ordered if not m.audio_only]
    first_day = next((m.recorded_at.date() for m in video if m.recorded_at), None)
    seen_before: set[str] = set()
    reports = []
    for m in ordered:
        mine = heard.get(m.id, set())
        if m.kind is not None:
            kind = m.kind
        elif m.audio_only:
            kind = SourceKind.VOICEOVER
        elif first_day is None or m.recorded_at is None or m.recorded_at.date() == first_day:
            kind = SourceKind.MAIN
        elif mine and len(mine & seen_before) >= 0.5 * len(mine):
            kind = SourceKind.RETAKE
        else:
            kind = SourceKind.PICKUP
        if not m.audio_only:
            seen_before |= mine
        reports.append(SourceReport(
            m, kind, len(mine), sum(1 for s in chosen.values() if s == m.id),
            sum(1 for _, _, later in overridden if later == m.id)))
    missing = tuple(c.unit.id for c in alignment.choices if c.chosen is None)
    return SourceMap(tuple(reports), chosen, tuple(overridden), missing)
