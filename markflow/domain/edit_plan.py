"""edit_plan.json — the contract between MarkFlow modules.

Every stage reads a plan and returns a new plan; only `infra/prproj/writer` turns it into a .prproj.
All times are integer Premiere ticks (254 016 000 000 per second): exact, no float drift,
directly writable into the project.

Changing any model here requires SCHEMA_VERSION + 1, a migration in MIGRATIONS and a test
(tests/domain/test_edit_plan.py locks the JSON schema by hash).
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Annotated, Any, Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 3   # v2: Source.width/height (optional); v3: subtitles (non-standard script instructions)

Ticks = Annotated[int, Field(ge=0)]


class PlanError(ValueError):
    """The plan is internally inconsistent or cannot be migrated."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)


class Stage(str, Enum):
    DRAFT = "MF1_draft"
    JOKES = "MF2_jokes"
    SFX = "MF3_sfx"
    MUSIC = "MF4_music"
    SIZES = "MF5_sizes"
    QA = "MF6_qa"


class SourceKind(str, Enum):
    MAIN = "main"            # main talking-head shoot
    RETAKE = "retake"        # re-recorded later, wins over main
    PICKUP = "pickup"        # extra lines recorded separately (добор)
    VOICEOVER = "voiceover"  # studio VO
    LIVE = "live"            # downloaded video insert
    ASSET = "asset"          # music, SFX, graphics from the user's folders


class LabelColor(str, Enum):
    """Premiere Pro label colours (Preferences > Labels, default names)."""

    VIOLET = "Violet"
    IRIS = "Iris"
    CARIBBEAN = "Caribbean"
    LAVENDER = "Lavender"
    CERULEAN = "Cerulean"
    FOREST = "Forest"
    ROSE = "Rose"
    MANGO = "Mango"
    PURPLE = "Purple"
    BLUE = "Blue"
    TEAL = "Teal"
    MAGENTA = "Magenta"
    TAN = "Tan"
    GREEN = "Green"
    BROWN = "Brown"
    YELLOW = "Yellow"


class ClipReason(str, Enum):
    SCRIPT = "script"                        # matches a script line
    IMPROV_MEANINGFUL = "improv_meaningful"  # off-script but meaningful: kept, coloured
    IMPROV_FUNNY = "improv_funny"            # off-script and funny: kept, coloured (bloopers)
    LIVE = "live"                            # live in the main flow
    LIVE_OVERLAY = "live_overlay"            # live over a highlighted fragment
    VOICEOVER = "voiceover"
    ASSET = "asset"


class MarkerKind(str, Enum):
    SCRIPT_COMMENT = "script_comment"  # comment from the Google Doc
    CHECK = "check"                    # ПРОВЕРИТЬ: a doubtful decision
    COMMAND = "command"                # editor command cut out of the take
    LIVE_MISSING = "live_missing"      # live not downloaded
    JOKE = "joke"
    INFO = "info"


class Source(_Model):
    id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    kind: SourceKind
    fps: str = Field(description="exact rate, e.g. '60', '30000/1001'")
    duration: Ticks
    has_video: bool = True
    audio_channels: int = Field(default=2, ge=0)
    content_hash: str | None = None
    width: int | None = Field(default=None, gt=0, description="picture size: the writer fits it into the frame")
    height: int | None = Field(default=None, gt=0)


class Sequence(_Model):
    name: str = Field(min_length=1)
    fps: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class Clip(_Model):
    """One cut of one source placed on the timeline, video and its audio linked."""

    id: str = Field(min_length=1)
    source_id: str
    source_in: Ticks
    source_out: Ticks
    start: Ticks = Field(description="timeline position")
    video_track: int | None = Field(default=None, ge=0, description="0 = V1; None = audio only")
    audio_tracks: tuple[int, ...] = Field(default=(), description="explicit A-track per audio channel, 0 = A1")
    reason: ClipReason = ClipReason.SCRIPT
    color: LabelColor | None = None
    script_ref: str | None = Field(default=None, description="id of the script block/line it covers")
    note: str = ""

    @model_validator(mode="after")
    def _check(self) -> "Clip":
        if self.source_out <= self.source_in:
            raise ValueError(f"clip {self.id}: source_out must be after source_in")
        if self.video_track is None and not self.audio_tracks:
            raise ValueError(f"clip {self.id}: needs a video track or at least one audio track")
        if len(set(self.audio_tracks)) != len(self.audio_tracks) or any(t < 0 for t in self.audio_tracks):
            raise ValueError(f"clip {self.id}: audio tracks must be distinct and >= 0")
        return self

    @property
    def duration(self) -> int:
        return self.source_out - self.source_in

    @property
    def end(self) -> int:
        return self.start + self.duration


class Marker(_Model):
    id: str = Field(min_length=1)
    start: Ticks
    duration: Ticks = 0
    name: str = ""
    comment: str = ""
    kind: MarkerKind = MarkerKind.INFO
    color: LabelColor | None = None
    script_ref: str | None = None


class TextLayer(_Model):
    """Plain text on the timeline, e.g. a live that could not be downloaded."""

    id: str = Field(min_length=1)
    start: Ticks
    duration: Ticks = Field(gt=0)
    video_track: int = Field(ge=0)
    text: str = Field(min_length=1)
    script_ref: str | None = None


class Subtitle(_Model):
    """A non-standard instruction from the script shown as a subtitle on its own track (PLAN 5.1)."""

    id: str = Field(min_length=1)
    start: Ticks
    duration: Ticks = Field(gt=0)
    track: int = Field(default=0, ge=0, description="0 = the first subtitle track")
    text: str = Field(min_length=1)
    note: str = ""
    script_ref: str | None = None


class TrackPreset(_Model):
    """An audio preset applied to a whole track (Audio Track Mixer)."""

    audio_track: int = Field(ge=0)
    preset: str = Field(min_length=1, description="preset name or path from the user's presets")
    params: dict[str, float] = Field(default_factory=dict)


class EditPlan(_Model):
    schema_version: int = SCHEMA_VERSION
    episode: str = Field(min_length=1)
    profile: str = Field(min_length=1)
    stage: Stage = Stage.DRAFT
    sequence: Sequence
    sources: tuple[Source, ...] = ()
    clips: tuple[Clip, ...] = ()
    markers: tuple[Marker, ...] = ()
    text_layers: tuple[TextLayer, ...] = ()
    subtitles: tuple[Subtitle, ...] = ()
    track_presets: tuple[TrackPreset, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> "EditPlan":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_version {self.schema_version} != {SCHEMA_VERSION}; migrate first")
        problems = consistency_problems(self)
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def duration(self) -> int:
        ends = [c.end for c in self.clips] + [t.start + t.duration for t in self.text_layers]
        return max(ends, default=0)

    def clips_on_video_track(self, track: int) -> list[Clip]:
        return sorted((c for c in self.clips if c.video_track == track), key=lambda c: c.start)

    def clips_on_audio_track(self, track: int) -> list[Clip]:
        return sorted((c for c in self.clips if track in c.audio_tracks), key=lambda c: c.start)


def _overlaps(spans: list[tuple[int, int, str]]) -> list[str]:
    spans = sorted(spans)
    return [
        f"{a_id} overlaps {b_id}"
        for (a_start, a_end, a_id), (b_start, b_end, b_id) in zip(spans, spans[1:])
        if b_start < a_end
    ]


def consistency_problems(plan: EditPlan) -> list[str]:
    """Cross-object rules: unique ids, known sources, clips inside sources, no overlaps per track."""
    problems: list[str] = []
    ids = [s.id for s in plan.sources]
    for group in (ids, [c.id for c in plan.clips], [m.id for m in plan.markers], [t.id for t in plan.text_layers],
                  [u.id for u in plan.subtitles]):
        dupes = sorted({i for i in group if group.count(i) > 1})
        if dupes:
            problems.append(f"duplicate ids: {dupes}")
    sources = {s.id: s for s in plan.sources}
    for clip in plan.clips:
        src = sources.get(clip.source_id)
        if src is None:
            problems.append(f"clip {clip.id}: unknown source {clip.source_id}")
            continue
        if clip.source_out > src.duration:
            problems.append(f"clip {clip.id}: source_out beyond source duration")
        if clip.video_track is not None and not src.has_video:
            problems.append(f"clip {clip.id}: source {src.id} has no video")
        if len(clip.audio_tracks) > src.audio_channels:
            problems.append(f"clip {clip.id}: more audio tracks than source channels")
    video: dict[int, list[tuple[int, int, str]]] = {}
    audio: dict[int, list[tuple[int, int, str]]] = {}
    for clip in plan.clips:
        if clip.video_track is not None:
            video.setdefault(clip.video_track, []).append((clip.start, clip.end, clip.id))
        for track in clip.audio_tracks:
            audio.setdefault(track, []).append((clip.start, clip.end, clip.id))
    for layer in plan.text_layers:
        video.setdefault(layer.video_track, []).append((layer.start, layer.start + layer.duration, layer.id))
    subs: dict[int, list[tuple[int, int, str]]] = {}
    for sub in plan.subtitles:
        subs.setdefault(sub.track, []).append((sub.start, sub.start + sub.duration, sub.id))
    for track, spans in sorted(subs.items()):
        problems += [f"S{track + 1}: {p}" for p in _overlaps(spans)]
    for track, spans in sorted(video.items()):
        problems += [f"V{track + 1}: {p}" for p in _overlaps(spans)]
    for track, spans in sorted(audio.items()):
        problems += [f"A{track + 1}: {p}" for p in _overlaps(spans)]
    return problems


# ---------- serialisation & migrations (strings only: the domain never touches files) ----------

# MIGRATIONS[n] turns a version-n dict into a version-(n+1) dict.
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    # v1 -> v2: sources gained optional width/height; old plans simply have none (no fit-to-frame scale written)
    1: lambda d: {**d, "sources": [{**s, "width": s.get("width"), "height": s.get("height")}
                                    for s in d.get("sources", [])]},
    # v2 -> v3: plans gained subtitles; old plans have none
    2: lambda d: {**d, "subtitles": d.get("subtitles", [])},
}


def migrate(data: dict[str, Any], migrations: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] | None = None,
            target: int = SCHEMA_VERSION) -> dict[str, Any]:
    steps = MIGRATIONS if migrations is None else migrations
    version = data.get("schema_version")
    if not isinstance(version, int):
        raise PlanError("edit plan has no integer schema_version")
    if version > target:
        raise PlanError(f"edit plan version {version} is newer than this MarkFlow ({target})")
    while version < target:
        if version not in steps:
            raise PlanError(f"no migration from edit plan version {version}")
        data = steps[version](dict(data))
        version += 1
        data["schema_version"] = version
    return data


def to_json(plan: EditPlan) -> str:
    return plan.model_dump_json(indent=2)


def from_json(text: str) -> EditPlan:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlanError(f"edit plan is not valid JSON: {exc}") from exc
    return EditPlan.model_validate(migrate(data))


def json_schema() -> dict[str, Any]:
    return EditPlan.model_json_schema()
