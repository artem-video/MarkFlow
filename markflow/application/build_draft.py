"""Stage 2.5 use case: script + transcribed sources -> edit_plan.json (MF1_draft, cut only)."""

from __future__ import annotations

from dataclasses import dataclass

from markflow.domain.align import Alignment, SourceText, align, script_units
from markflow.domain.commands import OffScriptRules
from markflow.domain.cut import CutSettings, RoughCut, build_flow, finish, improv_to_markers, repeat_report, trim_seams
from markflow.domain.edit_plan import EditPlan, Sequence
from markflow.domain.loudness import Envelope, silence_threshold
from markflow.domain.metrics import DraftMetrics, measure
from markflow.domain.profile import Profile
from markflow.domain.script_model import Script
from markflow.domain.timeline import assemble
from markflow.domain.transcript import Transcript
from markflow.shared.timecode import parse_fps
from markflow.domain.triage_rules import SourceMap, SourceMeta, classify_sources, recording_order


@dataclass(frozen=True)
class SourceInput:
    meta: SourceMeta
    transcript: Transcript      # merged transcript (stage 2.1)
    envelope: Envelope


@dataclass(frozen=True)
class DraftResult:
    plan: EditPlan
    alignment: Alignment
    cut: RoughCut
    source_map: SourceMap
    metrics: DraftMetrics
    repeats: tuple[str, ...] = ()


def cut_settings(profile: Profile) -> CutSettings:
    c = profile.cut
    return CutSettings(silence_db=c.silence_db, max_pause=c.max_pause_s, handle=c.handle_s, min_piece=c.min_clip_s)


def build_draft(script: Script, inputs: list[SourceInput], profile: Profile, sequence: Sequence,
                episode: str, lives: dict[str, SourceMeta] | None = None,
                live_windows: dict[str, list[tuple[float, float]]] | None = None) -> DraftResult:
    if not inputs:
        raise ValueError("no sources")
    ordered = recording_order([i.meta for i in inputs])
    by_id = {i.meta.id: i for i in inputs}
    texts = [SourceText.from_transcript(by_id[m.id].transcript, order, m.audio_only)
             for order, m in enumerate(ordered)]
    units = script_units(script)
    alignment = align(units, texts)
    settings = cut_settings(profile)
    written = [line for b in script.blocks for line in b.lines] + [c.words for b in script.blocks for c in b.clocks]
    rules = OffScriptRules(crew_names=tuple(profile.cut.crew_names))
    sources = {t.source_id: t for t in texts}
    envelopes = {i.meta.id: i.envelope for i in inputs}
    frames = {m.id: 1 / float(parse_fps(m.fps)) for m in ordered if m.fps}
    seq_frame = 1 / float(parse_fps(sequence.fps))
    thresholds = {sid: silence_threshold(env.db, settings.silence_db) for sid, env in envelopes.items()}
    rough = trim_seams(improv_to_markers(finish(build_flow(alignment, sources, rules, settings, written), sources,
                                                envelopes, settings, frames, seq_frame, thresholds)), sources)
    source_map = classify_sources(ordered, alignment)
    plan = assemble(script, rough, ordered, source_map, profile, sequence, episode, lives, live_windows)
    metrics = measure(plan, alignment, rough, envelopes, profile.cut.silence_db, thresholds)
    return DraftResult(plan, alignment, rough, source_map, metrics, tuple(repeat_report(rough, sources)))
