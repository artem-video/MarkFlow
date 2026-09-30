"""Timeline assembly (stage 2.5): script order + rough cut -> EditPlan. Pure.

Order follows the script. Spoken blocks get their pieces; lives/quotes get a placeholder of the right
length with a text layer (the writer shows it as a marker until stage 4 downloads the lives);
directions, parts, script comments, commands and doubtful places become markers. Improvisation kept
in the flow is coloured; bloopers go after the end with a gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from fractions import Fraction

from markflow.domain.align import word_sim
from markflow.domain.cut import Piece, RoughCut
from markflow.domain.edit_plan import (
    Clip, ClipReason, EditPlan, LabelColor, Marker, MarkerKind, Sequence, Source, SourceKind, Stage, TextLayer,
)
from markflow.domain.profile import Profile
from markflow.domain.script_model import CHECK_RU, BlockKind, Script, ScriptBlock
from markflow.domain.triage_rules import SourceMap, SourceMeta
from markflow.shared.links import live_key
from markflow.shared.text_norm import normalize
from markflow.shared.timecode import format_clock, parse_fps, seconds_to_ticks, ticks_per_frame

LIVE_DEFAULT_S = 5.0
LIVE_MAX_S = 120.0
QUOTE_S = 4.0
BLOOPERS_GAP_S = 5.0


@dataclass
class _Builder:
    profile: Profile
    sequence: Sequence
    metas: dict[str, SourceMeta]
    kinds: dict[str, SourceKind]
    clips: list[Clip] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    layers: list[TextLayer] = field(default_factory=list)
    cursor: int = 0

    def __post_init__(self) -> None:
        self.frame = ticks_per_frame(parse_fps(self.sequence.fps))

    def frames(self, seconds: float, minimum: int = 1) -> int:
        return max(minimum, round(seconds_to_ticks(seconds) / self.frame)) * self.frame

    def marker(self, kind: MarkerKind, name: str, comment: str = "", ref: str | None = None,
               at: int | None = None, duration: int = 0) -> None:
        colors = {
            MarkerKind.CHECK: self.profile.markers.check_color,
            MarkerKind.SCRIPT_COMMENT: self.profile.markers.script_comment_color,
            MarkerKind.COMMAND: self.profile.markers.command_color,
            MarkerKind.LIVE_MISSING: self.profile.markers.live_missing_color,
        }
        self.markers.append(Marker(
            id=f"m{len(self.markers) + 1:04d}", start=self.cursor if at is None else at, duration=duration,
            name=name[:120], comment=comment, kind=kind, color=colors.get(kind), script_ref=ref))

    def add_piece(self, piece: Piece, reason: ClipReason, color: LabelColor | None) -> int:
        meta = self.metas[piece.source_id]
        v, a = self.profile.tracks.video, self.profile.tracks.audio
        channels = min(meta.audio_channels, len(a.voice))
        src_frame = ticks_per_frame(parse_fps(meta.fps)) if meta.fps else self.frame
        src_in = round(seconds_to_ticks(max(0.0, piece.start)) / src_frame) * src_frame  # cuts are frame-snapped
        last = self.clips[-1] if self.clips else None
        if last is not None and last.source_id == piece.source_id and last.end == self.cursor \
                and abs(last.source_out - seconds_to_ticks(piece.start)) < self.frame:
            src_in = last.source_out  # a through-edit stays seamless
        duration = self.frames(piece.end - piece.start)
        src_total = seconds_to_ticks(meta.duration)
        if src_in + duration > src_total:
            duration = max(self.frame, ((src_total - src_in) // self.frame) * self.frame)
        if last is not None and last.source_id == piece.source_id and last.end == self.cursor \
                and last.source_out == src_in and last.reason == reason and last.color == color:
            # the same recording continues without a gap: one clip, no through-edit bar in Premiere
            refs = [x for x in (last.script_ref or "").split(",") if x] \
                + [x for x in (",".join(piece.unit_ids) or piece.block_id or "").split(",") if x]
            self.clips[-1] = last.model_copy(update={
                "source_out": last.source_out + duration,
                "script_ref": ",".join(dict.fromkeys(refs)),
                "note": (last.note + " " + piece.text)[:200]})
            start = self.cursor
            self.cursor += duration
            return start
        clip = Clip(
            id=f"c{len(self.clips) + 1:04d}", source_id=piece.source_id, source_in=src_in,
            source_out=src_in + duration, start=self.cursor,
            video_track=None if meta.audio_only else v.talking_head,
            audio_tracks=tuple(a.voice[:max(1, channels)]), reason=reason, color=color,
            script_ref=",".join(piece.unit_ids) or piece.block_id, note=piece.text[:200])
        self.clips.append(clip)
        start = self.cursor
        self.cursor += duration
        return start

    def add_live(self, meta: SourceMeta, start_s: float, end_s: float, block: ScriptBlock) -> int:
        """A downloaded live in the main flow: the window start..end of the file on the lives tracks (V3, A3-A4)."""
        v, a = self.profile.tracks.video.lives, self.profile.tracks.audio.lives
        channels = min(max(1, meta.audio_channels), len(a))
        try:
            src_frame = ticks_per_frame(parse_fps(meta.fps)) if meta.fps else self.frame
        except ValueError:  # odd variable-rate files (some TikToks, 29.583 fps): use the sequence's frame grid
            src_frame = self.frame
        src_in = round(seconds_to_ticks(max(0.0, start_s)) / src_frame) * src_frame  # on the file's own frame grid
        duration = self.frames(end_s - start_s)
        total = seconds_to_ticks(meta.duration)
        if src_in + duration > total:
            duration = max(self.frame, ((total - src_in) // self.frame) * self.frame)
        self.clips.append(Clip(
            id=f"c{len(self.clips) + 1:04d}", source_id=meta.id, source_in=src_in, source_out=src_in + duration,
            start=self.cursor, video_track=v, audio_tracks=tuple(a[:channels]), reason=ClipReason.LIVE,
            color=self.profile.colors.live, script_ref=block.id,
            note=f"ЛАЙВ {block.number or ''} {block.label}".strip()[:200]))
        start = self.cursor
        self.cursor += duration
        return start

    def placeholder(self, block: ScriptBlock, seconds: float, text: str) -> None:
        duration = self.frames(seconds)
        self.layers.append(TextLayer(id=f"t{len(self.layers) + 1:04d}", start=self.cursor, duration=duration,
                                     video_track=self.profile.tracks.video.text_layers, text=text,
                                     script_ref=block.id))
        self.cursor += duration


def _anchor_span(pieces: list[tuple[int, Piece]], piece_start: dict[int, int], piece_dur: dict[int, int],
                 anchor: str) -> tuple[int, int] | None:
    """(start, length) in ticks of the phrase a comment is attached to, following how it is pronounced.

    The anchor is the script's wording, the pieces hold the spoken words: match the first words loosely, then
    follow the phrase word by word; inside a clip a word sits at its share of the clip's length."""
    target = normalize(anchor).split()
    if not target:
        return None
    flat: list[tuple[int, int, int]] = []  # (piece, index in piece, words in piece)
    words: list[str] = []
    for i, p in pieces:
        if i not in piece_start:
            continue
        w = normalize(p.text).split()
        flat += [(i, k, len(w)) for k in range(len(w))]
        words += w
    head = target[:3]
    for s in range(len(words) - len(head) + 1):
        if all(word_sim(a, b) >= 0.8 for a, b in zip(words[s:s + len(head)], head)):
            e = min(len(words) - 1, s + len(target) - 1)
            pi, k, n = flat[s]
            pj, k2, n2 = flat[e]
            t0 = piece_start[pi] + piece_dur[pi] * k // n
            t1 = piece_start[pj] + piece_dur[pj] * (k2 + 1) // n2
            return t0, max(0, t1 - t0)
    return None


def _live_text(block: ScriptBlock) -> str:
    head = " ".join(x for x in ("ЛАЙВ" if block.kind != BlockKind.QUOTE else "ЦИТАТА", block.number or "", block.label)
                    if x)
    lines = [head]
    lines += list(block.links) or ["ссылки нет — см. комментарии"]
    for c in block.clocks:
        rng = format_clock(c.start) + (f"–{format_clock(c.end)}" if c.end is not None else "")
        lines.append(f"{rng} {c.words}".strip())
    lines += [f"• {n}" for n in block.notes]
    if block.kind == BlockKind.QUOTE:
        lines += list(block.lines)
    return "\n".join(lines)


def live_segments(block: ScriptBlock, total: float) -> list[tuple[float, float]]:
    """(start, end) seconds in the live's file for every timecode of the block, clipped to the file.

    A single time without an end ('0:26') is a moment the author points at: LIVE_DEFAULT_S from it."""
    if not block.clocks:  # «заставка (в начале)»: no timecode means the start of the file
        return [(0.0, min(LIVE_DEFAULT_S, total))]
    out = []
    for c in block.clocks:
        a = c.start
        b = c.end if c.end is not None and 0 < c.end - a <= LIVE_MAX_S else a + LIVE_DEFAULT_S
        if a >= total:
            continue
        out.append((a, min(b, total)))
    return out


def _live_seconds(block: ScriptBlock) -> float:
    if block.kind == BlockKind.QUOTE:
        return QUOTE_S
    total = sum(c.end - c.start for c in block.clocks if c.end is not None and 0 < c.end - c.start <= LIVE_MAX_S)
    return total or LIVE_DEFAULT_S


def assemble(script: Script, cut: RoughCut, metas: list[SourceMeta], source_map: SourceMap, profile: Profile,
             sequence: Sequence, episode: str, lives: dict[str, SourceMeta] | None = None,
             live_windows: dict[str, list[tuple[float, float]]] | None = None) -> EditPlan:
    """lives: live_key(link) -> the downloaded file; a link that is not there stays a text layer + marker.
    live_windows: block id -> refined (start, end) in the file per timecode (application.lives); else the script's."""
    live_windows = live_windows or {}
    lives = lives or {}
    kinds = {r.meta.id: r.kind for r in source_map.sources}
    kinds.update({m.id: SourceKind.LIVE for m in lives.values()})
    metas = list({m.id: m for m in list(metas) + list(lives.values())}.values())  # one source per file
    b = _Builder(profile, sequence, {m.id: m for m in metas}, kinds)
    by_block: dict[str, list[tuple[int, Piece]]] = {}
    for i, p in enumerate(cut.pieces):
        by_block.setdefault(p.block_id or "", []).append((i, p))
    cut_markers: dict[int, list] = {}
    for m in cut.markers:
        cut_markers.setdefault(m.after_piece, []).append(m)
    piece_start: dict[int, int] = {}
    piece_dur: dict[int, int] = {}
    comments = {c.id: c for c in script.comments}

    for block in script.blocks:
        block_start = b.cursor
        for check in block.checks:
            b.marker(MarkerKind.CHECK, f"{profile.markers.check_name}: {CHECK_RU.get(check, check)}",
                     block.header or block.text[:200], block.id)
        if block.spoken:
            pieces = by_block.get(block.id, [])
            if not pieces:
                b.marker(MarkerKind.CHECK, f"{profile.markers.check_name}: блок не найден в исходниках",
                         block.text[:500], block.id)
            for i, p in pieces:
                reason = {"improv_funny": ClipReason.IMPROV_FUNNY, "improv_meaningful": ClipReason.IMPROV_MEANINGFUL}
                if p.kind in reason:
                    color = (profile.colors.improv_funny if p.kind == "improv_funny"
                             else profile.colors.improv_meaningful)
                    piece_start[i] = b.add_piece(p, reason[p.kind], color)
                else:
                    kind = ClipReason.VOICEOVER if block.kind == BlockKind.VOICEOVER else ClipReason.SCRIPT
                    piece_start[i] = b.add_piece(p, kind, profile.colors.voiceover if kind == ClipReason.VOICEOVER
                                                 else None)
                    piece_dur[i] = b.cursor - piece_start[i]
                    for check in dict.fromkeys(p.checks):
                        b.marker(MarkerKind.CHECK, f"{profile.markers.check_name}: {check}", p.text[:300],
                                 ",".join(p.unit_ids), at=piece_start[i])
                for m in cut_markers.pop(i, []):
                    kind = MarkerKind.COMMAND if m.kind == "command" else \
                        MarkerKind.INFO if m.kind == "improv" else MarkerKind.CHECK
                    b.marker(kind, m.text[:120], m.text, block.id)
        elif block.kind in (BlockKind.LIVE, BlockKind.QUOTE, BlockKind.BUTT):
            text = _live_text(block)
            meta = lives.get(live_key(block.links[0])) if block.links else None
            segs = (live_windows.get(block.id) or live_segments(block, meta.duration)) if meta else []
            if segs:
                for a, z in segs:  # a placed live needs no marker
                    b.add_live(meta, a, z, block)
            else:  # a missing live gets a red marker as long as the live would be
                seconds = _live_seconds(block)
                b.marker(MarkerKind.LIVE_MISSING, text.split("\n")[0], text, block.id, duration=b.frames(seconds))
                b.placeholder(block, seconds, text)
        elif block.kind == BlockKind.INSERT:
            b.marker(MarkerKind.INFO, "стендап, записанный отдельно", "\n".join((block.header,) + block.links),
                     block.id)
        else:  # direction, part
            text = block.text or block.header
            b.marker(MarkerKind.INFO, text[:120], text + ("\n" + "\n".join(block.links) if block.links else ""),
                     block.id)
        # script comments at the fragment they are attached to
        for cid in block.comment_ids:
            c = comments[cid]
            if c.resolved:
                continue
            at, length = block_start, 0
            if c.anchor_text and block.spoken:
                span = _anchor_span(by_block.get(block.id, []), piece_start, piece_dur, c.anchor_text)
                if span:
                    at, length = span
                else:
                    needle = normalize(c.anchor_text)[:40]
                    for i, p in by_block.get(block.id, []):
                        if needle and needle in normalize(p.text) and i in piece_start:
                            at = piece_start[i]
                            break
            body = c.text + ("".join(f"\n↳ {r}" for r in c.replies)) + (f"\n[к тексту: {c.anchor_text}]"
                                                                         if c.anchor_text else "")
            b.marker(MarkerKind.SCRIPT_COMMENT, c.text[:120], body, block.id, at=at, duration=length)  # no author

    for m in cut_markers.pop(-1, []):
        b.marker(MarkerKind.CHECK, m.text[:120], m.text, at=0)
    for m in [m for ms in cut_markers.values() for m in ms if m.after_piece >= 0]:
        b.marker(MarkerKind.CHECK if m.kind == "check" else MarkerKind.INFO if m.kind == "improv"
                 else MarkerKind.COMMAND, m.text[:120], m.text)

    if False and (cut.bloopers or cut_markers.get(-2)):  # bloopers are not exported to the timeline
        b.cursor += b.frames(BLOOPERS_GAP_S)
        b.marker(MarkerKind.INFO, "БЛУПЕРСЫ: импровизация вне дублей", "всё, что сказано не по сценарию и не вошло")
        for m in cut_markers.get(-2, []):
            b.marker(MarkerKind.COMMAND, m.text[:120], m.text)
        for p in cut.bloopers:
            color = profile.colors.improv_funny if p.kind == "improv_funny" else profile.colors.improv_meaningful
            reason = ClipReason.IMPROV_FUNNY if p.kind == "improv_funny" else ClipReason.IMPROV_MEANINGFUL
            b.add_piece(p, reason, color)

    used = {c.source_id for c in b.clips}
    sources = tuple(
        Source(id=m.id, path=m.path, kind=kinds.get(m.id, SourceKind.MAIN), fps=m.fps or sequence.fps,
               duration=seconds_to_ticks(m.duration), has_video=not m.audio_only,
               audio_channels=max(1, m.audio_channels), width=m.width or None, height=m.height or None)
        for m in metas if m.id in used)
    return EditPlan(episode=episode, profile=profile.channel.id, stage=Stage.DRAFT, sequence=sequence,
                    sources=sources, clips=tuple(b.clips), markers=tuple(b.markers), text_layers=tuple(b.layers))


def seconds(ticks: int) -> float:
    return float(Fraction(ticks, 254_016_000_000))
