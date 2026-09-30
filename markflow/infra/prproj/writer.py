"""Write an EditPlan into a copy of a project that real Premiere saved (stage 3.2).

The ONLY module allowed to save a .prproj (CLAUDE.md). Rules:
- the base project is never modified: the result is a new file (refuses to overwrite the base or any
  existing file);
- sources already imported in the base are reused; missing ones get master clips created from the files
  (infra/prproj/media.py, values from ffprobe) — the base can be an empty template with one empty
  target sequence with enough tracks;
- only new objects are added; existing ones stay byte-identical except the lists that receive them
  (the target sequence's tracks, links and markers). Checked by validator.untouched_problems.

Object shapes are copied from items Premiere 26 (project version 45) saved itself — see anatomy.md.
"""

from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path

from lxml import etree

from markflow.domain.edit_plan import Clip, EditPlan, LabelColor, Marker, TextLayer
from markflow.infra.prproj.project import (
    AUDIO_MEDIA_TYPE, VIDEO_MEDIA_TYPE, Project, ProjectError, el, norm_path, sub,
)
from markflow.infra.prproj.media import MediaImporter, MediaSpec, spec_from_probe
from markflow.shared.timecode import parse_fps, ticks_per_frame

VIDEO_ITEM_CLASS = "368b0406-29e3-4923-9fcd-094fbf9a1089"
AUDIO_ITEM_CLASS = "064ec682-9ba6-11d5-af2d-9ca32c7d6164"
SUBCLIP_CLASS = "e0c58dc9-dbdd-4166-aef7-5db7e3f22e84"
VIDEO_CHAIN_CLASS = "0970e08a-f58f-4108-b29a-1a717b8e12e2"
AUDIO_CHAIN_CLASS = "3cb131d1-d3c0-47ae-a19a-bdf75ea11674"
AUDIO_FILTER_CLASS = "d77a90a0-6c9e-44bf-9b20-de8c21168fe1"
MUTE_PARAM_CLASS = "32657501-3aa4-445f-a49b-d09ecb9fa1ae"
LEVEL_PARAM_CLASS = "a714635e-a628-4b27-9d59-77eba47dbc1a"
SECONDARY_CLASS = "f9d004b5-cb04-4e2f-af6f-64fadc2c4be9"
LINK_CLASS = "149d4ea5-a7d4-4b34-9bb7-16d783904bf2"
MARKER_CLASS = "a45508e0-3ff7-4d04-90a7-2e0dfff4c910"
MARKERS_CLASS = "bee50706-b524-416c-9f03-b596ce5f6866"
ZERO_DB = "0.17782799899578094"  # Premiere's clip volume value for 0 dB

# Premiere label order (Preferences > Labels). The ints for 0–7 are the ones seen next to these names in
# Artem's projects; 8–15 are placeholders. Which one Premiere displays (name index or int) is checked in gate 3.
LABEL_INDEX = {c: i for i, c in enumerate(LabelColor)}
LABEL_RGB = {0: 9176648, 1: 6769408, 2: 480554, 3: 8851829, 4: 14910691, 5: 19005, 6: 3474060, 7: 5814353,
             8: 11405886, 9: 10016297, 10: 12953888, 11: 13924519, 12: 7046574, 13: 3585338, 14: 3289700,
             15: 1758419}


class WriteError(ProjectError):
    pass


class _Writer:
    def __init__(self, project: Project, plan: EditPlan, sequence_name: str,
                 media: dict[str, MediaSpec] | None = None, project_path: str | None = None):
        self.p, self.plan = project, plan
        self.media = {norm_path(k): v for k, v in (media or {}).items()}
        self.project_path = project_path
        self.seq = project.sequence(sequence_name)
        self.seq_id = self.seq.findtext("ID") or "1"
        self.video_tracks = project.tracks(self.seq, VIDEO_MEDIA_TYPE)
        self.audio_tracks = project.tracks(self.seq, AUDIO_MEDIA_TYPE)
        self.width, self.height = project.frame_size(self.seq)

    # ---------- checks before touching anything ----------

    def check(self) -> dict[str, etree._Element]:
        problems = []
        if any(self.p.track_items(t) for t in self.video_tracks + self.audio_tracks if t is not None):
            problems.append(f"sequence {self.seq.findtext('Name')!r} is not empty: MarkFlow fills an empty one")
        want = ticks_per_frame(parse_fps(self.plan.sequence.fps))
        if self.p.frame_ticks(self.seq) != want:
            problems.append(f"sequence frame rate differs from the plan ({self.plan.sequence.fps} fps)")
        v_need = max([c.video_track for c in self.plan.clips if c.video_track is not None] + [-1]) + 1
        a_need = max([t for c in self.plan.clips for t in c.audio_tracks] + [-1]) + 1
        if v_need > len(self.video_tracks):
            problems.append(f"sequence has {len(self.video_tracks)} video tracks, plan needs {v_need}")
        if a_need > len(self.audio_tracks):
            problems.append(f"sequence has {len(self.audio_tracks)} audio tracks, plan needs {a_need}")
        by_path = self.p.master_clips_by_path()
        by_name: dict[str, list[etree._Element]] = {}
        for path, mc in by_path.items():
            by_name.setdefault(path.rsplit("/", 1)[-1], []).append(mc)
        masters: dict[str, etree._Element] = {}
        missing = []
        importer: MediaImporter | None = None
        for s in self.plan.sources:
            mc = by_path.get(norm_path(s.path))
            if mc is None:
                same_name = by_name.get(norm_path(s.path).rsplit("/", 1)[-1], [])
                mc = same_name[0] if len(same_name) == 1 else None
            if mc is None and norm_path(s.path) in self.media:
                if importer is None:
                    importer = MediaImporter(self.p, self.project_path)
                mc = importer.add(self.media[norm_path(s.path)])
            if mc is None:
                missing.append(s.path)
                continue
            video, audio = self.p.master_clip_parts(mc)
            if s.has_video and video is None:
                problems.append(f"{s.path}: the imported clip has no video")
            used = max((len(c.audio_tracks) for c in self.plan.clips if c.source_id == s.id), default=0)
            channels = self._channels(audio[0]) if audio else 0
            if used > channels:
                problems.append(f"{s.path}: plan uses {used} audio channels, the clip has {channels}")
            masters[s.id] = mc
        if missing:
            problems.append("import these files into the base project in Premiere and save it: " + "; ".join(missing))
        if problems:
            raise WriteError("cannot write the plan:\n- " + "\n- ".join(problems))
        return masters

    @staticmethod
    def _channels(audio_clip: etree._Element) -> int:
        return len(audio_clip.findall("SecondaryContents/SecondaryContentItem"))

    # ---------- objects ----------

    def _item_clip(self, master_clip: etree._Element, clip: Clip, channel: int | None) -> etree._Element:
        """Copy of the master clip's Video/AudioClip with its own id, in/out, label (and channel)."""
        new = copy.deepcopy(master_clip)
        new.set("ObjectID", self.p.new_id())
        new.tail = None
        inner = new.find("Clip")
        node = inner.find("Node")
        if node is not None:
            inner.remove(node)
        if clip.color is not None:
            node = el("Node", Version="1")
            props = sub(node, "Properties", Version="1")
            index = LABEL_INDEX[clip.color]
            sub(props, "asl.clip.label.color", str(LABEL_RGB[index]))
            sub(props, "asl.clip.label.name", f"BE.Prefs.LabelColors.{index}")
            inner.insert(0, node)
        inner.find("ClipID").text = self.p.new_guid()
        scale = new.find("ScaleToFrameSize")
        if scale is not None:
            scale.text = "true"  # 1080p takes in a 4K sequence fill the frame (Premiere's «Scale to Frame Size»)
        for tag in ("InPoint", "OutPoint"):
            old = inner.find(tag)
            if old is not None:
                inner.remove(old)
        anchor = inner.find("FrameRate")
        if anchor is None:
            anchor = inner.find("InUse")
        pos = list(inner).index(anchor) if anchor is not None else len(inner)
        inner.insert(pos, el("OutPoint", str(clip.source_out)))
        inner.insert(pos, el("InPoint", str(clip.source_in)))
        if channel is not None:
            items = new.find("SecondaryContents")
            master_items = items.findall("SecondaryContentItem")
            master_sc = self.p.ref(master_items[channel])
            for it in master_items:
                items.remove(it)
            sc = el("SecondaryContent", ObjectID=self.p.new_id(), ClassID=SECONDARY_CLASS, Version="1")
            sub(sc, "Content", ObjectRef=master_sc.find("Content").get("ObjectRef"))
            sub(sc, "ChannelIndex", str(channel))
            self.p.add_object(sc)
            sub(items, "SecondaryContentItem", Index="0", ObjectRef=sc.get("ObjectID"))
            for tag in ("SecondaryIndex", "AudioChannelLayout"):
                old = new.find(tag)
                if old is not None:
                    new.remove(old)
            sub(new, "SecondaryIndex", str(channel))
            sub(new, "AudioChannelLayout", '[{"channellabel":0}]')
        return self.p.add_object(new)

    def _subclip(self, master: etree._Element, clip_el: etree._Element) -> etree._Element:
        s = el("SubClip", ObjectID=self.p.new_id(), ClassID=SUBCLIP_CLASS, Version="6")
        sub(s, "Clip", ObjectRef=clip_el.get("ObjectID"))
        sub(s, "MasterClip", ObjectURef=master.get("ObjectUID"))
        sub(s, "OrigChGrp", "0")
        sub(s, "Name", master.findtext("Name") or "")
        return self.p.add_object(s)

    def _track_item(self, cls: str, media_type: str, track: int, clip: Clip, subclip: etree._Element,
                    chain: etree._Element, video: bool) -> etree._Element:
        item = el("VideoClipTrackItem" if video else "AudioClipTrackItem", ObjectID=self.p.new_id(), ClassID=cls,
                  Version="8" if video else "11")
        cti = sub(item, "ClipTrackItem", Version="8")
        owner = sub(cti, "ComponentOwner", Version="1")
        sub(owner, "Components", ObjectRef=chain.get("ObjectID"))
        ti = sub(cti, "TrackItem", Version="4")
        sub(ti, "TrackIndex", str(track))
        sub(ti, "TrackRefCount", "1")
        if clip.start:
            sub(ti, "Start", str(clip.start))
        sub(ti, "End", str(clip.end))
        sub(ti, "MediaType", media_type)
        sub(ti, "Type", "1")
        sub(cti, "SubClip", ObjectRef=subclip.get("ObjectID"))
        sub(cti, "LinkRefCount", "0")
        sub(cti, "GroupRefCount", "0")
        sub(cti, "IsMuted", "false")
        if video:
            sub(item, "FrameRect", f"0,0,{self.width},{self.height}")
            sub(item, "PixelAspectRatio", "1,1")
            sub(item, "ToneMapSettings", '{"peak":-1,"version":2}')
        else:
            sub(item, "ID", self.p.new_guid())
        return self.p.add_object(item)

    def _video_chain(self) -> etree._Element:
        c = el("VideoComponentChain", ObjectID=self.p.new_id(), ClassID=VIDEO_CHAIN_CLASS, Version="3")
        sub(c, "DefaultMotion", "true")
        sub(c, "DefaultOpacity", "true")
        sub(c, "DefaultMotionComponentID", "2")
        sub(c, "DefaultOpacityComponentID", "1")
        cc = sub(c, "ComponentChain", Version="3")
        self._chain_node(cc)
        sub(cc, "NextComponentID", "3")
        sub(c, "SeqID", self.seq_id)
        return self.p.add_object(c)

    @staticmethod
    def _chain_node(cc: etree._Element) -> None:
        node = sub(cc, "Node", Version="1")
        props = sub(node, "Properties", Version="1")
        sub(props, "MZ.ComponentChain.ActiveComponentID", "1")
        sub(props, "MZ.ComponentChain.ActiveComponentParamIndex", "4294967295")

    def _audio_chain(self) -> etree._Element:
        mute = el("AudioComponentParam", ObjectID=self.p.new_id(), ClassID=MUTE_PARAM_CLASS, Version="10")
        sub(mute, "RangeLocked", "false")
        sub(mute, "Timestamp", "0")
        sub(mute, "Name", "Mute")
        level = el("AudioComponentParam", ObjectID=self.p.new_id(), ClassID=LEVEL_PARAM_CLASS, Version="10")
        sub(level, "StartKeyframe", f"-91445760000000000,{ZERO_DB[:14]},0,0,0,0,0,0")
        sub(level, "CurrentValue", ZERO_DB)
        sub(level, "RangeLocked", "false")
        sub(level, "UnitsString", "dB")
        sub(level, "Timestamp", "0")
        sub(level, "Name", "Level")
        self.p.add_object(mute)
        self.p.add_object(level)
        f = el("AudioFilterComponent", ObjectID=self.p.new_id(), ClassID=AUDIO_FILTER_CLASS, Version="4")
        ac = sub(f, "AudioComponent", Version="3")
        comp = sub(ac, "Component", Version="7")
        params = sub(comp, "Params", Version="1")
        sub(params, "Param", Index="0", ObjectRef=mute.get("ObjectID"))
        sub(params, "Param", Index="1", ObjectRef=level.get("ObjectID"))
        sub(comp, "Intrinsic", "true")
        sub(comp, "ID", "1")
        sub(ac, "AudioChannelLayout", '[{"channellabel":0}]')
        sub(ac, "ChannelType", "0")
        sub(ac, "FrameRate", "5292000")
        sub(ac, "AudioComponentType", "0")
        sub(f, "FilterPreset", "0")
        sub(f, "FilterMatchName", "Internal Volume Mono")
        sub(f, "FilterIndex", "-1")
        sub(f, "ChannelConfigData",
            '{"in":[{"layout":[0],"name":"Mono In","type":0}],"out":[{"layout":[0],"name":"Mono Out","type":0}]}')
        self.p.add_object(f)
        c = el("AudioComponentChain", ObjectID=self.p.new_id(), ClassID=AUDIO_CHAIN_CLASS, Version="4")
        cc = sub(c, "ComponentChain", Version="3")
        self._chain_node(cc)
        comps = sub(cc, "Components", Version="1")
        sub(comps, "Component", Index="0", ObjectRef=f.get("ObjectID"))
        sub(cc, "NextComponentID", "2")
        return self.p.add_object(c)

    def _append_to_track(self, track: etree._Element, item: etree._Element) -> None:
        clip_items = track.find("ClipTrack/ClipItems")
        items = clip_items.find("TrackItems")
        if items is None:
            items = el("TrackItems", Version="1")
            clip_items.insert(0, items)
        sub(items, "TrackItem", Index=str(len(items)), ObjectRef=item.get("ObjectID"))

    def _link(self, items: list[etree._Element]) -> None:
        link = el("Link", ObjectID=self.p.new_id(), ClassID=LINK_CLASS, Version="1")
        group = sub(sub(link, "TrackItemGroup", Version="1"), "TrackItems", Version="1")
        for i, it in enumerate(items):
            sub(group, "TrackItem", Index=str(i), ObjectRef=it.get("ObjectID"))
            it.find("ClipTrackItem/LinkRefCount").text = "1"
        self.p.add_object(link)
        pgc = self.seq.find("PersistentGroupContainer")
        if pgc is None:
            pgc = el("PersistentGroupContainer", Version="1")
            self.seq.insert(list(self.seq).index(self.seq.find("TrackGroups")), pgc)
        lc = pgc.find("LinkContainer")
        if lc is None:
            lc = sub(pgc, "LinkContainer", Version="1")
        links = lc.find("Links")
        if links is None:
            links = sub(lc, "Links", Version="1")
        sub(links, "Link", Index=str(len(links)), ObjectRef=link.get("ObjectID"))

    def _marker_list(self) -> etree._Element:
        """A sequence that never had a marker (the empty template) has no MarkerOwner: add the same shape
        Premiere writes (MarkerOwner right after Node -> Markers object with ByGUID/state fields)."""
        container = el("Markers", ObjectID=self.p.new_id(), ClassID=MARKERS_CLASS, Version="4")
        sub(container, "ByGUID", "byGUID")
        sub(container, "LastMetadataState", "00000000-0000-0000-0000-000000000000")
        sub(container, "LastContentState", "00000000-0000-0000-0000-000000000000")
        self.p.add_object(container)
        owner = self.seq.find("MarkerOwner")
        if owner is None:
            owner = el("MarkerOwner", Version="1")
            node = self.seq.find("Node")
            self.seq.insert(list(self.seq).index(node) + 1 if node is not None else 0, owner)
        for old in owner.findall("Markers"):
            owner.remove(old)
        sub(owner, "Markers", ObjectRef=container.get("ObjectID"))
        return container

    def _marker(self, start: int, name: str, comment: str) -> None:
        container = self.p.ref(self.seq.find("MarkerOwner/Markers"))
        if container is None:
            container = self._marker_list()
        guid = self.p.new_guid()
        payload = {"DVAMarker": {"mComment": comment, "mMarkerID": guid, "mName": name,
                                 "mStartTime": {"ticks": start}, "mType": "Comment"}}
        marker = el("Marker", ObjectID=self.p.new_id(), ClassID=MARKER_CLASS, Version="3")
        sub(marker, "DVAMarker", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        self.p.add_object(marker)
        lst = container.find("Markers")
        if lst is None:
            lst = el("Markers", Version="1")
            container.insert(0, lst)
        entry = sub(lst, "Marker", Version="1", Index=str(len(lst)))
        sub(entry, "First", guid)
        sub(entry, "Second", ObjectRef=marker.get("ObjectID"))

    # ---------- plan ----------

    def write(self) -> None:
        masters = self.check()
        for clip in sorted(self.plan.clips, key=lambda c: c.start):
            master = masters[clip.source_id]
            video_clip, audio_clips = self.p.master_clip_parts(master)
            linked = []
            if clip.video_track is not None:
                c = self._item_clip(video_clip, clip, None)
                item = self._track_item(VIDEO_ITEM_CLASS, VIDEO_MEDIA_TYPE, clip.video_track, clip,
                                        self._subclip(master, c), self._video_chain(), video=True)
                self._append_to_track(self.video_tracks[clip.video_track], item)
                linked.append(item)
            for channel, track in enumerate(clip.audio_tracks):
                c = self._item_clip(audio_clips[0], clip, channel)
                item = self._track_item(AUDIO_ITEM_CLASS, AUDIO_MEDIA_TYPE, track, clip,
                                        self._subclip(master, c), self._audio_chain(), video=False)
                self._append_to_track(self.audio_tracks[track], item)
                linked.append(item)
            if len(linked) > 1:
                self._link(linked)
        for m in sorted(self.plan.markers, key=lambda m: m.start):
            self._marker(m.start, _marker_name(m), _marker_comment(m))
        for t in self.plan.text_layers:
            self._marker(t.start, t.text.split("\n")[0][:120], _layer_comment(t))


def _marker_name(m: Marker) -> str:
    return m.name or m.kind.value


def _marker_comment(m: Marker) -> str:
    return m.comment


def _layer_comment(t: TextLayer) -> str:
    seconds = t.duration / 254_016_000_000
    return f"[текстовый слой V{t.video_track + 1}, {seconds:.1f} с]\n{t.text}"


def probe_media(plan: EditPlan) -> dict[str, MediaSpec]:
    """ffprobe every source of the plan (for master clips the base project does not have yet)."""
    from markflow.infra.media.ffmpeg import FfmpegAudio

    audio = FfmpegAudio(Path("."))
    return {s.path: spec_from_probe(s.path, audio.probe(Path(s.path))) for s in plan.sources if Path(s.path).is_file()}


def write_plan(base: Path, plan: EditPlan, out: Path, sequence_name: str,
               media: dict[str, MediaSpec] | None = None) -> Project:
    """Write `plan` into a copy of `base` at `out` (a new file). Returns the written project.

    media: path -> MediaSpec for sources the base has not imported; probed with ffprobe when None.
    """
    base, out = Path(base), Path(out)
    if out.resolve() == base.resolve():
        raise WriteError("refusing to overwrite the base project")
    if out.exists():
        raise WriteError(f"{out} already exists: MarkFlow never overwrites a project")
    project = Project.load(base)
    if media is None:
        media = probe_media(plan)
    _Writer(project, plan, sequence_name, media, str(out)).write()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    tmp.write_bytes(gzip.compress(project.to_bytes(), compresslevel=6))
    tmp.replace(out)
    return project


def write_into(project: Project, plan: EditPlan, sequence_name: str,
               media: dict[str, MediaSpec] | None = None) -> Project:
    """In-memory variant (tests, dry runs)."""
    _Writer(project, plan, sequence_name, media).write()
    return project
