"""Master clips for source files, created inside a project Premiere saved (stage 3.2).

The base template (templates/<channel>/MF_base.prproj) is an empty project: no source is imported.
Instead of asking the editor to import the files by hand, the writer adds, per source file, the same
object graph Premiere 26 writes when it imports a file (seen in the real episode, anatomy.md):

    RootProjectItem/Items -> ClipProjectItem -> MasterClip -> ClipLoggingInfo
                                                         -> VideoComponentChain / AudioComponentChain
                                                         -> VideoClip -> VideoMediaSource -> Media -> VideoStream
                                                         -> AudioClip -> AudioMediaSource -> Media -> AudioStream
                                                                      -> SecondaryContent (one per channel)
                                                         -> ClipChannelGroupVectorSerializer -> ... per channel

Values come from ffprobe. Fields Premiere recomputes on open (peak files, content hashes, colour space)
are left out; Premiere re-reads the file header when it opens the project.
"""

from __future__ import annotations

import ntpath
import os
from dataclasses import dataclass
from fractions import Fraction

from lxml import etree

from markflow.infra.prproj.project import Project, ProjectError, el, sub
from markflow.shared.timecode import TICKS_PER_SECOND, parse_fps, ticks_per_frame

CLIP_PROJECT_ITEM_CLASS = "cb4e0ed7-aca1-4171-8525-e3658dec06dd"
MASTER_CLIP_CLASS = "fb11c33a-b0a9-4465-aa94-b6d5db2628cf"
LOGGING_INFO_CLASS = "77ab7fdd-dcdf-465d-9906-7a330ca1e738"
AUDIO_CHAIN_CLASS = "3cb131d1-d3c0-47ae-a19a-bdf75ea11674"
VIDEO_CHAIN_CLASS = "0970e08a-f58f-4108-b29a-1a717b8e12e2"
VIDEO_CLIP_CLASS = "9308dbef-2440-4acb-9ab2-953b9a4e82ec"
AUDIO_CLIP_CLASS = "b8830d03-de02-41ee-84ec-fe566dc70cd9"
MARKERS_CLASS = "bee50706-b524-416c-9f03-b596ce5f6866"
VIDEO_MEDIA_SOURCE_CLASS = "e64ddf74-8fac-4682-8aa8-0e0ca2248949"
AUDIO_MEDIA_SOURCE_CLASS = "f588da05-fc2a-4fbc-9383-74d653b379e3"
MEDIA_CLASS = "7a5c103e-f3ac-4391-b6b4-7cc3d2f9a7ff"
VIDEO_STREAM_CLASS = "a36e4719-3ec6-4a0c-ab11-8b4aab377aa5"
AUDIO_STREAM_CLASS = "0b5cf52f-2b85-4863-890b-8844b64ecfe9"
SECONDARY_CLASS = "f9d004b5-cb04-4e2f-af6f-64fadc2c4be9"
CHANNEL_GROUPS_CLASS = "a3127a8c-95d4-456e-a7f5-171b3f922426"
CHANNEL_VECTOR_CLASS = "333d203b-3a53-4195-8894-fc7523ff3dc7"
CHANNEL_CLASS = "5c89aa7a-89a6-4483-becd-f2b1def42316"
IMPORTER_ID = "1fa18bfa-255c-44b1-ad73-56bcd99fceaf"   # the importer Premiere 26 used for MP4, MOV and WAV
DEF_MAPPING_ID = "0551e2a0-6da1-4691-800e-b3ded5ca94f7"
AUDIO_RATE_48K = 5_292_000  # ticks per sample at 48 kHz

# ClipLoggingInfo/TimecodeFormat as Premiere wrote it: 102 = 29.97 drop, 108 = 60, 200 = audio samples
TIMECODE_FORMAT = {Fraction(30000, 1001): "102", Fraction(60): "108", Fraction(25): "101", Fraction(30): "104",
                   Fraction(24000, 1001): "100", Fraction(24): "106", Fraction(50): "107",
                   Fraction(60000, 1001): "103"}


@dataclass(frozen=True)
class MediaSpec:
    """What the writer needs to know about a source file (from ffprobe)."""
    path: str                  # absolute Windows path
    duration_s: float
    fps: str | None            # exact 'r_frame_rate' ('30000/1001', '60/1'); None = audio only
    width: int | None = None
    height: int | None = None
    audio_channels: int = 2
    audio_rate: int = 48_000
    codec_tag: str | None = None

    @property
    def has_video(self) -> bool:
        return self.fps is not None


def fourcc(tag: str | None) -> int | None:
    if not tag or len(tag) != 4:
        return None
    return int.from_bytes(tag.encode("latin-1"), "big")


def _channel_layout(n: int) -> str:
    if n == 2:
        return '[{"channellabel":100},{"channellabel":101}]'
    if n == 1:
        return '[{"channellabel":0}]'
    return "[" + ",".join('{"channellabel":%d}' % (1000 + k) for k in range(n)) + "]"


def _channel_type(n: int) -> str:
    return {1: "0", 2: "1"}.get(n, "2")


class MediaImporter:
    """Adds master clips to `project` (in memory). One per path; a path already imported is reused."""

    def __init__(self, project: Project, project_path: str | None = None):
        self.p = project
        self.project_path = project_path
        self._node_id = self._max_node_id() + 1

    def _max_node_id(self) -> int:
        best = 1_000_000
        for e in self.p.root.iter("Node"):
            text = e.findtext("ID")
            if text and text.isdigit():
                best = max(best, int(text))
        return best

    def _next_node_id(self) -> str:
        nid = str(self._node_id)
        self._node_id += 1
        return nid

    def _root_items(self) -> etree._Element:
        roots = self.p.objects("RootProjectItem")
        if len(roots) != 1:
            raise ProjectError("the base project has no single root bin")
        items = roots[0].find("ProjectItemContainer/Items")
        if items is None:
            container = roots[0].find("ProjectItemContainer")
            if container is None:
                container = sub(roots[0], "ProjectItemContainer", Version="1")
            items = sub(container, "Items", Version="1")
        return items

    def _relative(self, path: str) -> str:
        if not self.project_path:
            return path
        try:
            return ntpath.relpath(path, ntpath.dirname(self.project_path))
        except ValueError:  # another drive
            return path

    def add(self, spec: MediaSpec) -> etree._Element:
        """Create the master clip of one file. Returns the MasterClip element."""
        p = self.p
        name = ntpath.basename(spec.path)
        duration = round(Fraction(spec.duration_s) * TICKS_PER_SECOND)
        rate = parse_fps(spec.fps) if spec.has_video else None
        try:
            frame = ticks_per_frame(rate) if rate else None
        except ValueError:  # variable-rate file (some TikToks, 29.583 fps): snap to the nearest standard rate
            standard = [Fraction(n, d) for n, d in ((24000, 1001), (24, 1), (25, 1), (30000, 1001), (30, 1),
                                                    (50, 1), (60000, 1001), (60, 1))]
            frame = ticks_per_frame(min(standard, key=lambda s: abs(s - Fraction(rate))))
        if frame:
            duration = (duration // frame) * frame
        channels = max(0, spec.audio_channels)
        audio_rate_ticks = TICKS_PER_SECOND // spec.audio_rate if spec.audio_rate else AUDIO_RATE_48K

        media = el("Media", ObjectUID=p.new_guid(), ClassID=MEDIA_CLASS, Version="30")
        video_stream = audio_stream = None
        if channels:
            audio_stream = el("AudioStream", ObjectID=p.new_id(), ClassID=AUDIO_STREAM_CLASS, Version="8")
            sub(audio_stream, "AudioChannelLayout", _channel_layout(channels))
            sub(audio_stream, "FrameRate", str(audio_rate_ticks))
            sub(audio_stream, "Duration", str(duration))
            p.add_object(audio_stream)
            sub(media, "AudioStream", ObjectRef=audio_stream.get("ObjectID"))
        if spec.has_video:
            video_stream = el("VideoStream", ObjectID=p.new_id(), ClassID=VIDEO_STREAM_CLASS, Version="22")
            sub(video_stream, "FrameRate", str(frame))
            sub(video_stream, "Duration", str(duration))
            code = fourcc(spec.codec_tag)
            if code is not None:
                sub(video_stream, "CodecType", str(code))
            sub(video_stream, "FrameRect", f"0,0,{spec.width or 1920},{spec.height or 1080}")
            sub(video_stream, "OriginalImageOrientationType", "1")
            p.add_object(video_stream)
            sub(media, "VideoStream", ObjectRef=video_stream.get("ObjectID"))
        sub(media, "RelativePath", self._relative(spec.path))
        sub(media, "FilePath", spec.path)
        sub(media, "ImplementationID", IMPORTER_ID)
        sub(media, "Title", name)
        sub(media, "FileKey", p.new_guid())
        sub(media, "ConformedAudioRate", str(AUDIO_RATE_48K))
        sub(media, "ActualMediaFilePath", spec.path)
        p.add_object(media)

        markers = el("Markers", ObjectID=p.new_id(), ClassID=MARKERS_CLASS, Version="4")
        sub(markers, "ByGUID", "byGUID")
        sub(markers, "LastMetadataState", "00000000-0000-0000-0000-000000000000")
        p.add_object(markers)

        def media_source(tag: str, cls: str) -> etree._Element:
            src = el(tag, ObjectID=p.new_id(), ClassID=cls, Version="2")
            ms = sub(src, "MediaSource", Version="4")
            sub(ms, "Content", Version="10")
            sub(ms, "Media", ObjectURef=media.get("ObjectUID"))
            sub(src, "OriginalDuration", str(duration))
            return p.add_object(src)

        def clip(tag: str, cls: str, version: str, source: etree._Element) -> etree._Element:
            c = el(tag, ObjectID=p.new_id(), ClassID=cls, Version=version)
            inner = sub(c, "Clip", Version="18")
            owner = sub(inner, "MarkerOwner", Version="1")
            sub(owner, "Markers", ObjectRef=markers.get("ObjectID"))
            sub(inner, "Source", ObjectRef=source.get("ObjectID"))
            sub(inner, "ClipID", p.new_guid())
            sub(inner, "InUse", "false")
            return c

        clips: list[etree._Element] = []
        video_chain = None
        if spec.has_video:
            vclip = clip("VideoClip", VIDEO_CLIP_CLASS, "11", media_source("VideoMediaSource", VIDEO_MEDIA_SOURCE_CLASS))
            p.add_object(vclip)
            clips.append(vclip)
            video_chain = el("VideoComponentChain", ObjectID=p.new_id(), ClassID=VIDEO_CHAIN_CLASS, Version="3")
            sub(video_chain, "ComponentChain", Version="3")
            p.add_object(video_chain)
        audio_chain = groups = None
        if channels:
            asrc = media_source("AudioMediaSource", AUDIO_MEDIA_SOURCE_CLASS)
            aclip = clip("AudioClip", AUDIO_CLIP_CLASS, "8", asrc)
            items = sub(aclip, "SecondaryContents", Version="1")
            for k in range(channels):
                sc = el("SecondaryContent", ObjectID=p.new_id(), ClassID=SECONDARY_CLASS, Version="1")
                sub(sc, "Content", ObjectRef=asrc.get("ObjectID"))
                sub(sc, "ChannelIndex", str(k))
                p.add_object(sc)
                sub(items, "SecondaryContentItem", Index=str(k), ObjectRef=sc.get("ObjectID"))
            sub(aclip, "AudioChannelLayout", _channel_layout(channels))
            p.add_object(aclip)
            clips.append(aclip)
            audio_chain = el("AudioComponentChain", ObjectID=p.new_id(), ClassID=AUDIO_CHAIN_CLASS, Version="4")
            sub(audio_chain, "DefaultVol", "true")
            sub(audio_chain, "DefaultVolumeComponentID", "1")
            sub(audio_chain, "DefaultChannelVolumeComponentID", "2")
            sub(audio_chain, "ComponentChain", Version="3")
            sub(audio_chain, "AudioChannelLayout", _channel_layout(channels))
            sub(audio_chain, "ChannelType", _channel_type(channels))
            p.add_object(audio_chain)
            chans = []
            for k in range(channels):
                ch = el("ClipChannelSerializer", ObjectID=p.new_id(), ClassID=CHANNEL_CLASS, Version="1")
                sub(ch, "SourceClipIndex", "0")
                sub(ch, "mSourceChannelIndex", str(k))
                chans.append(p.add_object(ch))
            vec = el("ClipChannelVectorSerializer", ObjectID=p.new_id(), ClassID=CHANNEL_VECTOR_CLASS, Version="1")
            cl = sub(vec, "ClipChannels", Version="1")
            for k, ch in enumerate(chans):
                sub(cl, "ClipChannelItem", Index=str(k), ObjectRef=ch.get("ObjectID"))
            sub(vec, "ChannelType", _channel_type(channels))
            p.add_object(vec)
            groups = el("ClipChannelGroupVectorSerializer", ObjectID=p.new_id(), ClassID=CHANNEL_GROUPS_CLASS,
                        Version="1")
            sub(sub(groups, "ClipChannelVectors", Version="1"), "ClipChannelVectorItem", Index="0",
                ObjectRef=vec.get("ObjectID"))
            p.add_object(groups)

        logging = el("ClipLoggingInfo", ObjectID=p.new_id(), ClassID=LOGGING_INFO_CLASS, Version="10")
        if not spec.has_video:
            sub(logging, "CaptureMode", "1")
        sub(logging, "ClipName", name)
        sub(logging, "TimecodeFormat", TIMECODE_FORMAT.get(rate, "102") if rate else "200")
        sub(logging, "MediaInPoint", "0")
        sub(logging, "MediaOutPoint", str(duration))
        sub(logging, "MediaFrameRate", str(frame or audio_rate_ticks))
        p.add_object(logging)

        master = el("MasterClip", ObjectUID=p.new_guid(), ClassID=MASTER_CLIP_CLASS, Version="12")
        node = sub(master, "Node", Version="1")
        props = sub(node, "Properties", Version="1")
        sub(props, "monitor.take.video", "true" if spec.has_video else "false")
        sub(props, "monitor.take.audio", "true")
        sub(node, "ID", self._next_node_id())
        sub(master, "LoggingInfo", ObjectRef=logging.get("ObjectID"))
        if audio_chain is not None:
            sub(sub(master, "AudioComponentChains", Version="1"), "AudioComponentChain", Index="0",
                ObjectRef=audio_chain.get("ObjectID"))
        if video_chain is not None:
            sub(master, "VideoComponentChain", ObjectRef=video_chain.get("ObjectID"))
        cl = sub(master, "Clips", Version="1")
        for k, c in enumerate(clips):
            sub(cl, "Clip", Index=str(k), ObjectRef=c.get("ObjectID"))
        if groups is not None:
            sub(master, "AudioClipChannelGroups", ObjectRef=groups.get("ObjectID"))
        sub(master, "DefMappingID", DEF_MAPPING_ID)
        sub(master, "Name", name)
        sub(master, "MasterClipChangeVersion", "1")
        p.add_object(master)

        item = el("ClipProjectItem", ObjectUID=p.new_guid(), ClassID=CLIP_PROJECT_ITEM_CLASS, Version="1")
        pi = sub(item, "ProjectItem", Version="1")
        inode = sub(pi, "Node", Version="1")
        sub(inode, "Properties", Version="1")
        sub(inode, "ID", self._next_node_id())
        sub(pi, "Name", name)
        sub(item, "MasterClip", ObjectURef=master.get("ObjectUID"))
        p.add_object(item)
        items = self._root_items()
        sub(items, "Item", Index=str(len(items)), ObjectURef=item.get("ObjectUID"))
        return master


def spec_from_probe(path: str, info) -> MediaSpec:
    """infra.media.ffmpeg.MediaInfo -> MediaSpec."""
    return MediaSpec(path=os.path.abspath(path) if os.name == "nt" else path, duration_s=info.duration,
                     fps=info.fps, width=info.width, height=info.height, audio_channels=info.audio_channels,
                     audio_rate=info.audio_rate or 48_000, codec_tag=info.video_codec_tag)
