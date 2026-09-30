"""Read what is on a sequence: tracks, clips (timeline + source window + file), markers."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from pathlib import Path

from markflow.infra.prproj.project import AUDIO_MEDIA_TYPE, VIDEO_MEDIA_TYPE, Project


@dataclass(frozen=True)
class TimelineItem:
    kind: str            # 'video' | 'audio'
    track: int           # 0 = V1 / A1
    start: int           # ticks on the timeline
    end: int
    in_point: int        # ticks in the source
    out_point: int
    media_path: str      # '' for nested sequences / graphics
    name: str
    object_id: str
    label: str | None = None

    @property
    def duration(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class MarkerInfo:
    start: int
    name: str
    comment: str


@dataclass(frozen=True)
class SequenceInfo:
    name: str
    frame_ticks: int
    width: int
    height: int
    video_tracks: int
    audio_tracks: int
    items: tuple[TimelineItem, ...] = field(default=())
    markers: tuple[MarkerInfo, ...] = field(default=())

    def on_track(self, kind: str, track: int) -> list[TimelineItem]:
        return sorted((i for i in self.items if i.kind == kind and i.track == track), key=lambda i: i.start)

    @property
    def duration(self) -> int:
        return max((i.end for i in self.items), default=0)


def item_info(project: Project, item, kind: str, track: int) -> TimelineItem:
    ti = item.find("ClipTrackItem/TrackItem")
    start = int(ti.findtext("Start") or 0)
    end = int(ti.findtext("End") or 0)
    subclip = project.ref(item.find("ClipTrackItem/SubClip"))
    clip = project.ref(subclip.find("Clip")) if subclip is not None else None
    in_point = int(clip.findtext("Clip/InPoint") or 0) if clip is not None else 0
    out_point = int(clip.findtext("Clip/OutPoint") or 0) if clip is not None else 0
    source = project.ref(clip.find("Clip/Source")) if clip is not None else None
    media = project.ref(source.find("MediaSource/Media")) if source is not None else None
    path = project.media_path(media) if media is not None and media.tag == "Media" else ""
    label = clip.findtext("Clip/Node/Properties/asl.clip.label.name") if clip is not None else None
    name = subclip.findtext("Name") if subclip is not None else ""
    return TimelineItem(kind, track, start, end, in_point, out_point, path, name or "", item.get("ObjectID"), label)


def read_markers(project: Project, seq) -> list[MarkerInfo]:
    container = project.ref(seq.find("MarkerOwner/Markers"))
    out = []
    if container is None:
        return out
    for m in container.findall("Markers/Marker"):
        marker = project.ref(m.find("Second"))
        if marker is None:
            continue
        try:
            data = json.loads(html.unescape(marker.findtext("DVAMarker") or "{}")).get("DVAMarker", {})
        except json.JSONDecodeError:
            continue
        out.append(MarkerInfo(int(data.get("mStartTime", {}).get("ticks", 0)), data.get("mName", ""),
                              data.get("mComment", "")))
    return sorted(out, key=lambda m: m.start)


def read_sequence(project: Project, name: str) -> SequenceInfo:
    seq = project.sequence(name)
    items = []
    for kind, media_type in (("video", VIDEO_MEDIA_TYPE), ("audio", AUDIO_MEDIA_TYPE)):
        for index, track in enumerate(project.tracks(seq, media_type)):
            for item in project.track_items(track):
                if item is not None:
                    items.append(item_info(project, item, kind, index))
    width, height = project.frame_size(seq)
    return SequenceInfo(
        name=name, frame_ticks=project.frame_ticks(seq), width=width, height=height,
        video_tracks=len(project.tracks(seq, VIDEO_MEDIA_TYPE)),
        audio_tracks=len(project.tracks(seq, AUDIO_MEDIA_TYPE)),
        items=tuple(items), markers=tuple(read_markers(project, seq)))


def read_project(path: Path) -> list[SequenceInfo]:
    project = Project.load(path)
    return [read_sequence(project, s.findtext("Name")) for s in project.sequences()
            if [x.findtext("Name") for x in project.sequences()].count(s.findtext("Name")) == 1]
