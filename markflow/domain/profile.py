"""Channel profile: every channel-specific rule and threshold lives in profiles/<channel>/profile.yaml.

A new client = a new folder, no code changes (CLAUDE.md). This module only defines and checks the shape;
reading the YAML is markflow/profiles/loader.py.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from markflow.domain.edit_plan import LabelColor
from markflow.domain.script_model import BlockKind, CueVocabulary


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Channel(_Model):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    language: str = "ru"


class ScriptRules(_Model):
    cues: dict[BlockKind, list[str]]
    end_words: list[str] = ["КОНЕЦ"]
    reserve_words: list[str] = ["РЕЗЕРВ"]

    def vocabulary(self) -> CueVocabulary:
        return CueVocabulary(
            kinds={k: tuple(v) for k, v in self.cues.items()},
            end_words=tuple(self.end_words),
            reserve_words=tuple(self.reserve_words),
        )


class CutRules(_Model):
    silence_db: float = Field(le=0, description="below this level = silence")
    max_pause_s: float = Field(gt=0, description="longer pauses are shortened to this")
    handle_s: float = Field(ge=0, description="margin kept before/after speech at every cut")
    min_clip_s: float = Field(default=0.3, gt=0)
    take_policy: str = Field(default="last", pattern=r"^(last|best)$")
    keep_improv: bool = True


class Colors(_Model):
    improv_meaningful: LabelColor
    improv_funny: LabelColor
    live: LabelColor | None = None
    voiceover: LabelColor | None = None


class Markers(_Model):
    check_name: str = "ПРОВЕРИТЬ"
    check_color: LabelColor
    script_comment_color: LabelColor
    command_color: LabelColor
    live_missing_color: LabelColor


class TrackRoles(_Model):
    """0-based track indices per role (0 = V1 / A1)."""

    talking_head: int = Field(ge=0)
    sizes: int = Field(ge=0)
    lives: int = Field(ge=0)
    images: list[int] = []
    graphics: list[int] = []
    text_layers: int = Field(ge=0)


class AudioRoles(_Model):
    voice: list[int]
    lives: list[int]
    music: list[int] = []
    sfx: list[int] = []
    bleep: list[int] = []


class Tracks(_Model):
    video: TrackRoles
    audio: AudioRoles

    @model_validator(mode="after")
    def _distinct(self) -> "Tracks":
        v = self.video
        fixed_video = [v.talking_head, v.sizes, v.lives, *v.images, *v.graphics]
        if len(set(fixed_video)) != len(fixed_video):
            raise ValueError("video track roles overlap")
        a = self.audio
        audio = [*a.voice, *a.lives, *a.music, *a.sfx, *a.bleep]
        if len(set(audio)) != len(audio):
            raise ValueError("audio track roles overlap")
        return self


class Lives(_Model):
    max_height: int = Field(default=1440, gt=0, description="download up to 2K, never re-encode")
    file_name: str = "{channel}_{title}_{id}"
    refine_window_s: float = Field(default=5.0, gt=0)
    fit_to_frame: bool = True


class Voice(_Model):
    preset: str | None = None
    presets_folder: str | None = None


class Assets(_Model):
    """Folders on the user's PC: referenced, never copied. Empty until set on the PC."""

    music: list[str] = []
    sfx: list[str] = []
    mogrt: list[str] = []
    templates: list[str] = []


class Bleep(_Model):
    mode: str = Field(pattern=r"^(partial|full|none)$")
    sound: str = ""


class Style(_Model):
    """Author's taste, for the thinking stages (jokes, SFX, music). Human version: STYLE.md."""

    core_idea: str = ""
    banned: list[str] = []
    liked: list[str] = []
    sounds: list[str] = []
    music_liked: list[str] = []
    music_banned: list[str] = []
    bleep: Bleep
    aliases: dict[str, list[str]] = {}
    red_lines: list[str] = []
    max_technique_repeats: int = Field(default=3, ge=1)


class Profile(_Model):
    profile_version: int = 1
    channel: Channel
    script: ScriptRules
    cut: CutRules
    colors: Colors
    markers: Markers
    tracks: Tracks
    lives: Lives = Lives()
    voice: Voice = Voice()
    assets: Assets = Assets()
    style: Style
    template: str | None = Field(default=None, description="path to a template.prproj saved by Premiere")
