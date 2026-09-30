""".prproj access: gzip XML, the root-level object table, id allocation, saving. See anatomy.md.

Only infra/prproj/writer.py may *save* a project (CLAUDE.md); everything else only loads.
"""

from __future__ import annotations

import gzip
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

VIDEO_MEDIA_TYPE = "228cda18-3625-4d2d-951e-348879e4ed93"
AUDIO_MEDIA_TYPE = "80b8e3d5-6dca-4195-aefb-cb5f407ab009"
DATA_MEDIA_TYPE = "d8143ffe-eec4-4d2a-a909-d5f7bf094dc5"
AUDIO_TICKS_PER_SAMPLE_48K = 5_292_000


class ProjectError(RuntimeError):
    pass


def norm_path(path: str) -> str:
    """Compare media paths across OS / case / slash styles."""
    return re.sub(r"[\\/]+", "/", path.strip()).lower()


@dataclass
class Project:
    root: etree._Element
    prolog: bytes
    source: str = ""

    def __post_init__(self) -> None:
        self.reindex()

    # ---------- loading ----------

    @staticmethod
    def load(path: Path) -> "Project":
        raw = Path(path).read_bytes()
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass  # an uncompressed project also opens
        return Project.from_bytes(raw, str(path))

    @staticmethod
    def from_bytes(raw: bytes, source: str = "") -> "Project":
        start = raw.find(b"<PremiereData")
        if start < 0:
            raise ProjectError(f"{source}: not a Premiere project (no <PremiereData>)")
        parser = etree.XMLParser(remove_blank_text=False, huge_tree=True)
        return Project(etree.fromstring(raw[start:], parser), raw[:start], source)

    def reindex(self) -> None:
        self.by_id: dict[str, etree._Element] = {}
        self.by_uid: dict[str, etree._Element] = {}
        for e in self.root:
            if e.get("ClassID") is None:
                continue
            if e.get("ObjectID") is not None:
                self.by_id[e.get("ObjectID")] = e
            if e.get("ObjectUID") is not None:
                self.by_uid[e.get("ObjectUID")] = e
        numeric = [int(k) for k in self.by_id if k.isdigit()]
        self._next_id = max(numeric, default=0) + 1

    # ---------- lookups ----------

    def ref(self, el: etree._Element | None) -> etree._Element | None:
        if el is None:
            return None
        if el.get("ObjectRef") is not None:
            return self.by_id.get(el.get("ObjectRef"))
        if el.get("ObjectURef") is not None:
            return self.by_uid.get(el.get("ObjectURef"))
        return None

    def objects(self, tag: str) -> list[etree._Element]:
        return [e for e in self.root if e.tag == tag and e.get("ClassID")]

    def sequences(self) -> list[etree._Element]:
        return self.objects("Sequence")

    def sequence(self, name: str) -> etree._Element:
        found = [s for s in self.sequences() if s.findtext("Name") == name]
        if not found:
            names = ", ".join(repr(s.findtext("Name")) for s in self.sequences())
            raise ProjectError(f"no sequence named {name!r}; the project has: {names}")
        if len(found) > 1:
            raise ProjectError(f"{len(found)} sequences are named {name!r}; rename them in Premiere")
        return found[0]

    def track_groups(self, seq: etree._Element) -> dict[str, etree._Element]:
        out = {}
        for tg in seq.findall("TrackGroups/TrackGroup"):
            out[tg.findtext("First")] = self.ref(tg.find("Second"))
        return out

    def tracks(self, seq: etree._Element, media_type: str) -> list[etree._Element]:
        group = self.track_groups(seq).get(media_type)
        if group is None:
            return []
        items = sorted(group.findall("TrackGroup/Tracks/Track"), key=lambda t: int(t.get("Index")))
        return [self.ref(t) for t in items]

    def track_items(self, track: etree._Element) -> list[etree._Element]:
        return [self.ref(t) for t in track.findall("ClipTrack/ClipItems/TrackItems/TrackItem")]

    def frame_ticks(self, seq: etree._Element) -> int:
        group = self.track_groups(seq).get(VIDEO_MEDIA_TYPE)
        return int(group.findtext("TrackGroup/FrameRate"))

    def frame_size(self, seq: etree._Element) -> tuple[int, int]:
        group = self.track_groups(seq).get(VIDEO_MEDIA_TYPE)
        rect = (group.findtext("FrameRect") or "0,0,1920,1080").split(",")
        return int(rect[2]), int(rect[3])

    def media_path(self, media: etree._Element) -> str:
        return media.findtext("ActualMediaFilePath") or media.findtext("FilePath") or ""

    def master_clips_by_path(self) -> dict[str, etree._Element]:
        """normalized media path -> MasterClip (sequences, which are master clips too, are skipped)."""
        out: dict[str, etree._Element] = {}
        for mc in self.objects("MasterClip"):
            clip = self.ref(mc.find("Clips/Clip"))
            source = self.ref(clip.find("Clip/Source")) if clip is not None else None
            media = self.ref(source.find("MediaSource/Media")) if source is not None else None
            if media is not None and media.tag == "Media":
                out[norm_path(self.media_path(media))] = mc
        return out

    def master_clip_parts(self, mc: etree._Element) -> tuple[etree._Element | None, list[etree._Element]]:
        """(video clip, audio clips) of a master clip."""
        clips = [self.ref(c) for c in mc.findall("Clips/Clip")]
        video = next((c for c in clips if c is not None and c.tag == "VideoClip"), None)
        audio = [c for c in clips if c is not None and c.tag == "AudioClip"]
        return video, audio

    # ---------- creating ----------

    def new_id(self) -> str:
        oid = str(self._next_id)
        self._next_id += 1
        return oid

    @staticmethod
    def new_guid() -> str:
        return str(uuid.uuid4())

    def add_object(self, el: etree._Element) -> etree._Element:
        """Append a root-level object with Premiere-like formatting."""
        last = self.root[-1] if len(self.root) else None
        if last is not None:
            last.tail = "\n\t"
        el.tail = "\n"
        self.root.append(el)
        if el.get("ObjectID") is not None:
            self.by_id[el.get("ObjectID")] = el
        if el.get("ObjectUID") is not None:
            self.by_uid[el.get("ObjectUID")] = el
        return el

    def to_bytes(self) -> bytes:
        body = etree.tostring(self.root, encoding="UTF-8", xml_declaration=False)
        return (self.prolog or b'<?xml version="1.0" encoding="UTF-8" ?>\n') + body + b"\n"


def el(tag: str, text: str | None = None, **attrs: str) -> etree._Element:
    e = etree.Element(tag, **{k: str(v) for k, v in attrs.items()})
    if text is not None:
        e.text = str(text)
    return e


def sub(parent: etree._Element, tag: str, text: str | None = None, **attrs: str) -> etree._Element:
    e = el(tag, text, **attrs)
    parent.append(e)
    return e
