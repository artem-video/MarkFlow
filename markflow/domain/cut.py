"""Rough cut (stages 2.3–2.4): chosen takes -> ordered speech pieces with clean boundaries. Pure.

- consecutive sentences taken from one continuous stretch of a recording become one piece;
- what was said between them is classified: command (cut, marker), improvisation (kept, coloured), junk (cut);
- improvisation that is not between two chosen takes goes to a bloopers tail (never silently removed);
- every boundary is moved into silence on the loudness envelope (never cut a live word), keeping a handle;
- long pauses inside a piece are shortened to the profile maximum (Phantom-style).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from markflow.domain.align import Alignment, Choice, Occurrence, SourceText, word_sim
from markflow.domain.commands import OffScript, OffScriptRules, classify
from markflow.domain.loudness import Envelope
from markflow.shared.text_norm import normalize

import numpy as np
from rapidfuzz import fuzz


@dataclass(frozen=True)
class CutSettings:
    silence_db: float = -60.0
    max_pause: float = 0.5
    handle: float = 0.04
    min_piece: float = 0.3
    search: float = 0.35          # how far a boundary may move looking for silence
    merge_gap: float = 15.0       # s: next sentence this close in the same recording = same piece


@dataclass(frozen=True)
class Piece:
    source_id: str
    start: float                  # seconds in the source
    end: float
    kind: str                     # 'script' | 'improv_funny' | 'improv_meaningful'
    unit_ids: tuple[str, ...] = ()
    block_id: str | None = None
    text: str = ""
    checks: tuple[str, ...] = ()

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class CutMarker:
    after_piece: int              # marker at the end of this piece (-1 = timeline start, -2 = bloopers tail)
    kind: str                     # 'command' | 'check'
    text: str


@dataclass(frozen=True)
class RoughCut:
    pieces: tuple[Piece, ...]
    markers: tuple[CutMarker, ...] = ()
    bloopers: tuple[Piece, ...] = ()
    missing: tuple[Choice, ...] = ()        # script sentences not found (ПРОВЕРИТЬ)
    junk_seconds: float = 0.0               # dropped between chosen takes
    unsafe_cuts: tuple[str, ...] = field(default=())  # boundaries that could not reach silence


# ---------- flow ----------

def _uncovered_runs(src: SourceText, lo: int, hi: int, covered: set[int]) -> list[tuple[int, int]]:
    runs, start = [], None
    for k in range(lo, hi):
        if k in covered:
            if start is not None:
                runs.append((start, k - 1))
                start = None
        elif start is None:
            start = k
    if start is not None:
        runs.append((start, hi - 1))
    return runs


def _text(src: SourceText, a: int, b: int) -> str:
    out, last = [], None
    for t in src.tokens[a:b + 1]:
        if t.raw is not last and t.raw != last:
            out.append(t.raw)
        last = t.raw
    return " ".join(out)


def _same(a: list[str], b: list[str]) -> bool:
    return len(a) == len(b) and all(word_sim(x, y) >= 0.8 for x, y in zip(a, b))


def _collapse_repeats(words: list[str]) -> list[str]:
    """'если вдруг если вдруг меня' -> 'если вдруг меня' (stutters and restarts, up to 10 words, ASR spelling
    differences tolerated: 'гоу стадия поможет … гоу стади поможет …')."""
    out = list(words)
    changed = True
    while changed:
        changed = False
        for n in range(min(10, len(out) // 2), 0, -1):
            i = 0
            while i + 2 * n <= len(out):
                if _same(out[i:i + n], out[i + n:i + 2 * n]):
                    del out[i:i + n]  # keep the later reading
                    changed = True
                else:
                    i += 1
    return out


class _ScriptText:
    """Everything written in the script, to recognise failed takes (a torn piece of a script line)."""

    def __init__(self, texts: list[str]):
        self.text = " | ".join(normalize(t) for t in texts if normalize(t))

    def is_failed_take(self, spoken: str) -> bool:
        words = normalize(spoken).split()
        collapsed = _collapse_repeats(words)
        if len(collapsed) < 2:
            return len(words) >= 2  # 'да да да': a stutter
        if len(collapsed) <= 0.6 * len(words):
            return True  # mostly restarts of the same words
        res = fuzz.partial_ratio_alignment(" ".join(collapsed), self.text, score_cutoff=75)
        return res is not None


RETAKE_WINDOW = 120.0  # s: a phrase repeated inside a take this soon after was a failed attempt
PHRASE_GAP = 0.4  # s: a pause this long splits phrases when the ASR gives no punctuation (GigaAM)


def _sentences(src: SourceText, a: int, b: int) -> list[tuple[int, int]]:
    """Split tokens a..b at sentence ends, '…' (a restart usually follows) and pauses."""
    out, start = [], a
    for k in range(a, b + 1):
        raw = src.tokens[k].raw.rstrip()
        last_of_word = k == b or src.tokens[k + 1].raw is not src.tokens[k].raw
        pause = k < b and last_of_word and src.tokens[k + 1].start - src.tokens[k].end >= PHRASE_GAP
        if last_of_word and (raw.endswith((".", "!", "?", "…", "...")) or pause):
            out.append((start, k))
            start = k + 1
    if start <= b:
        out.append((start, b))
    return out


def build_flow(alignment: Alignment, sources: dict[str, SourceText], rules: OffScriptRules,
               settings: CutSettings = CutSettings(), script_texts: list[str] | None = None) -> RoughCut:
    """script_texts: every line of the script (spoken, quotes, live words) — defaults to the aligned units."""
    covered: dict[str, set[int]] = {sid: set() for sid in sources}
    for sid, occs in alignment.occurrences.items():
        for o in occs:
            covered[sid].update(range(o.first, o.last + 1))
    written = _ScriptText(script_texts if script_texts is not None else [c.unit.text for c in alignment.choices])

    pieces: list[Piece] = []
    markers: list[CutMarker] = []
    missing: list[Choice] = []
    junk = 0.0
    used: dict[str, set[int]] = {sid: set() for sid in sources}
    prev: Occurrence | None = None
    prev_block: str | None = None

    def retaken_later(src: SourceText, a: int, b: int) -> bool:
        """The phrase is said again as part of a take within RETAKE_WINDOW s after it: a failed attempt."""
        words = normalize(_text(src, a, b)).split()
        if len(words) < 3:
            return False
        limit = src.tokens[b].end + RETAKE_WINDOW
        stop = b + 1
        while stop < len(src.tokens) and src.tokens[stop].start <= limit:
            stop += 1
        take = [src.tokens[k].word for k in range(b + 1, stop) if k in covered[src.source_id]]
        if len(take) >= 3 and fuzz.partial_ratio_alignment(" ".join(words), " ".join(take), score_cutoff=80):
            return True  # said again inside a script take
        if len(words) < 4:
            return False
        # said again later off-script too (an ad read or a cut line re-recorded): the last reading wins
        rest = " ".join(src.tokens[k].word for k in range(b + 1, stop))
        return fuzz.partial_ratio_alignment(" ".join(words), rest, score_cutoff=85) is not None

    def kind_of(src: SourceText, a: int, b: int) -> OffScript:
        text = _text(src, a, b)
        kind = classify(text, rules)
        if kind == OffScript.COMMAND:
            return kind
        if written.is_failed_take(text) or retaken_later(src, a, b):
            return OffScript.JUNK
        if kind == OffScript.IMPROV_MEANINGFUL and text.rstrip().endswith(("...", "…")):
            return OffScript.JUNK  # an abandoned phrase: the speaker restarts after it
        return kind

    def split_run(src: SourceText, a: int, b: int) -> list[tuple[int, int, OffScript]]:
        """Sentence by sentence, then neighbours of the same kind joined again."""
        if classify(_text(src, a, b), rules) == OffScript.COMMAND:
            return [(a, b, OffScript.COMMAND)]
        parts: list[list] = []
        for x, y in _sentences(src, a, b):
            kind = kind_of(src, x, y)
            if kind == OffScript.JUNK and len(normalize(_text(src, x, y)).split()) < rules.min_improv_words \
                    and parts and parts[-1][2] != OffScript.JUNK and not written.is_failed_take(_text(src, x, y)):
                kind = parts[-1][2]  # a short tail of an improvised phrase belongs to it
            if parts and parts[-1][2] == kind:
                parts[-1][1] = y
            else:
                parts.append([x, y, kind])
        return [(x, y, k) for x, y, k in parts]

    def add_script(choice: Choice, first: int | None = None) -> None:
        o = choice.chosen
        src = sources[o.source_id]
        a = o.first if first is None else first
        used[o.source_id].update(range(a, o.last + 1))
        pieces.append(Piece(o.source_id, src.tokens[a].start, o.end, "script", (choice.unit.id,),
                            choice.unit.block_id, _text(src, a, o.last), choice.checks))

    for choice in alignment.choices:
        o = choice.chosen
        if o is None:
            missing.append(choice)
            markers.append(CutMarker(len(pieces) - 1, "check", f"ПРОВЕРИТЬ: нет в исходниках — «{choice.unit.text}»"))
            prev = None
            continue
        same_stretch = (prev is not None and o.source_id == prev.source_id and prev_block == choice.unit.block_id
                        and o.last > prev.last and o.start - prev.end <= settings.merge_gap)
        if same_stretch and o.first <= prev.last:
            # overlapping matches of neighbouring sentences: one continuous reading
            src = sources[o.source_id]
            last = pieces[-1]
            pieces[-1] = replace(last, end=max(last.end, o.end), unit_ids=last.unit_ids + (choice.unit.id,),
                                 text=f"{last.text} {_text(src, prev.last + 1, o.last)}",
                                 checks=last.checks + choice.checks)
            used[o.source_id].update(range(prev.last + 1, o.last + 1))
            prev = o
            continue
        if not same_stretch:
            add_script(choice)
            prev, prev_block = o, choice.unit.block_id
            continue
        src = sources[o.source_id]
        runs = _uncovered_runs(src, prev.last + 1, o.first, covered[o.source_id])
        between_takes = any(k in covered[o.source_id] for k in range(prev.last + 1, o.first))
        for a, b, kind in [p for ra, rb in runs for p in split_run(src, ra, rb)]:
            text = _text(src, a, b)
            used[o.source_id].update(range(a, b + 1))
            if kind == OffScript.COMMAND:
                markers.append(CutMarker(len(pieces) - 1, "command", f"команда: «{text}»"))
            elif kind in (OffScript.IMPROV_FUNNY, OffScript.IMPROV_MEANINGFUL):
                pieces.append(Piece(o.source_id, src.tokens[a].start, src.tokens[b].end, kind.value,
                                    text=text, block_id=choice.unit.block_id))
            else:
                junk += src.tokens[b].end - src.tokens[a].start
        last = pieces[-1]
        if not runs and not between_takes and last.kind == "script":
            pieces[-1] = replace(last, end=o.end, unit_ids=last.unit_ids + (choice.unit.id,),
                                 text=f"{last.text} {_text(src, o.first, o.last)}",
                                 checks=last.checks + choice.checks)
            used[o.source_id].update(range(o.first, o.last + 1))
        else:
            add_script(choice)
        prev = o

    bloopers: list[Piece] = []
    notes: list[CutMarker] = []
    for sid, src in sources.items():
        runs = _uncovered_runs(src, 0, len(src.tokens), covered[sid] | used[sid])
        for a, b, kind in [p for ra, rb in runs for p in split_run(src, ra, rb)]:
            text = _text(src, a, b)
            if kind in (OffScript.IMPROV_FUNNY, OffScript.IMPROV_MEANINGFUL):
                bloopers.append(Piece(sid, src.tokens[a].start, src.tokens[b].end, kind.value, text=text))
            elif kind == OffScript.COMMAND and len(normalize(text).split()) >= 4:
                notes.append(CutMarker(-2, "command", f"со съёмки ({sid} {src.tokens[a].start:.0f} с): «{text}»"))
    return RoughCut(tuple(pieces), tuple(markers + notes), tuple(bloopers), tuple(missing), round(junk, 2))


# ---------- boundaries & pauses ----------

EDGE_MARGIN = 0.035   # s of silence kept on both sides of a (frame-snapped) cut: metric window + half a sequence frame
CLEAN_RUN = 2 * EDGE_MARGIN + 0.02  # s: a silent run long enough to hold a frame-snapped cut with margins
FORWARD_LOOK = 0.6
EXTEND = 1.2          # s: how far a boundary may grow over neighbouring words to reach a pause    # s: ASR puts a word start early after a pause — look this far into the first word


def _neighbours(src: SourceText, start: float, end: float) -> tuple[float, float, float, float]:
    """(start of the word before, end of the first word, start of the last word, end of the word after).

    ASR word times drift by up to a few hundred ms, so the search may cross ASR word edges; the envelope
    decides where the silence really is. Only the other words' far ends are hard limits."""
    before = [t for t in src.tokens if t.end <= start + 1e-6]
    inside = [t for t in src.tokens if t.start >= start - 1e-6 and t.end <= end + 1e-6]
    after = [t for t in src.tokens if t.start >= end - 1e-6]
    prev_start = max((t.start for t in before), default=0.0)
    first_end = inside[0].end if inside else end
    last_start = inside[-1].start if inside else start
    next_end = min((t.end for t in after), default=float("inf"))
    return prev_start, first_end, last_start, next_end


def _silent_runs(env: Envelope, lo: float, hi: float, threshold: float) -> list[tuple[float, float]]:
    """Runs of hops quieter than threshold inside [lo, hi) (clipped to the window)."""
    if hi - lo < env.hop:
        return []
    i, j = env._slice(lo, hi)
    quiet = np.concatenate(([False], env.db[i:j] < threshold, [False]))
    edges = np.flatnonzero(np.diff(quiet.astype(np.int8)))
    return [((i + a) * env.hop, (i + b) * env.hop) for a, b in zip(edges[0::2], edges[1::2])]


def _choose(near: list[tuple[float, float]], far: list[tuple[float, float]], t: float, edge: int,
            far_key) -> tuple[float, float] | None:
    """Clean pause next to the edge > clean pause over the neighbouring words > short dip next to the edge >
    short dip further away."""
    clean_near = [r for r in near if r[1] - r[0] >= CLEAN_RUN]
    clean_far = [r for r in far if r[1] - r[0] >= CLEAN_RUN]
    if clean_near:
        return _pick(clean_near, t, edge)
    if clean_far:
        return min(clean_far, key=far_key)
    if near:
        return _pick(near, t, edge)
    if far:
        return min(far, key=far_key)
    return None


def _pick(runs: list[tuple[float, float]], t: float, edge: int) -> tuple[float, float]:
    """The silent run holding t (ASR edge already in silence), else the one whose speech-side edge is nearest."""
    wide = [r for r in runs if r[1] - r[0] >= CLEAN_RUN]
    runs = wide or runs  # a 1–2 hop dip under the threshold is a poor place to cut when a real pause is near
    holding = [r for r in runs if r[0] <= t <= r[1]]
    if holding:
        return holding[0]
    return min(runs, key=lambda r: abs(r[edge] - t))


def _cut_in_run(a: float, b: float, speech_side: float, handle: float, into_run: int,
                frame: float | None = None) -> float:
    """A cut inside the silent run [a, b]: `handle` from the speech edge, at least EDGE_MARGIN from both ends,
    on the source's frame grid when its frame length is known (the timeline can only cut on frames)."""
    need = max(handle, EDGE_MARGIN)
    if b - a <= 2 * EDGE_MARGIN:
        t = (a + b) / 2
    else:
        t = min(max(speech_side - into_run * need, a + EDGE_MARGIN), b - EDGE_MARGIN)
    if frame:
        lo, hi = math.ceil((a + EDGE_MARGIN) / frame - 1e-9), math.floor((b - EDGE_MARGIN) / frame + 1e-9)
        if lo <= hi:
            k = min(max(round(t / frame), lo), hi)
        else:
            k = round(((a + b) / 2) / frame)
        t = k * frame
    return t


def refine(piece: Piece, src: SourceText, env: Envelope, s: CutSettings,
           frame: float | None = None) -> tuple[Piece, list[str]]:
    """Put both ends into real silence next to the speech edges on the envelope, never into other speech.

    ASR word times drift at silence edges: the start is searched from shortly before the ASR start (not before
    the previous word began) to well into the first word; the silent run closest to the ASR start wins and the
    cut goes `handle` before the sound onset, keeping a safety margin of silence on both sides.
    """
    warnings = []
    thr = s.silence_db
    prev_start, first_end, last_start, next_end = _neighbours(src, piece.start, piece.end)
    search = max(s.search, 0.5)

    lo = max(prev_start + 0.05, piece.start - search, 0.0)
    fwd = max(piece.start, min(first_end - 0.05, piece.start + FORWARD_LOOK, piece.end - s.min_piece))
    near = _silent_runs(env, lo, fwd + env.hop, thr)
    # no clean pause next to the ASR edge (speech runs on): take in the neighbouring word(s) up to the nearest
    # pause rather than cut a live word — a word too many is safer than a cut through sound
    far = _silent_runs(env, max(0.0, piece.start - EXTEND), lo, thr)
    run = _choose(near, far, piece.start, edge=1, far_key=lambda r: -r[1])
    if run:
        start = _cut_in_run(run[0], run[1], run[1], s.handle, 1, frame)
    else:
        start = env.quietest(lo, fwd + env.hop) if fwd - lo >= env.hop else piece.start
        warnings.append(f"{piece.source_id} {piece.start:.2f}s: начало реза не в тишине")

    back = min(piece.end, max(last_start + 0.05, piece.end - FORWARD_LOOK, start + s.min_piece))
    hi = min(next_end - 0.05, piece.end + search, env.duration)
    near = _silent_runs(env, back, hi, thr) if hi > back else []
    far = _silent_runs(env, max(hi, back), min(piece.end + EXTEND, env.duration), thr)
    run = _choose(near, far, piece.end, edge=0, far_key=lambda r: r[0])
    if run:
        end = _cut_in_run(run[0], run[1], run[0], s.handle, -1, frame)
    else:
        end = env.quietest(back, hi) if hi - back >= env.hop else piece.end
        warnings.append(f"{piece.source_id} {piece.end:.2f}s: конец реза не в тишине")
    return replace(piece, start=round(start, 6), end=round(max(end, start + s.min_piece), 6)), warnings


def shorten_pauses(piece: Piece, env: Envelope, s: CutSettings, frame: float | None = None) -> list[Piece]:
    """Split a piece at silences longer than max_pause, leaving max_pause of the pause (half on each side).

    No speech is dropped: every part between two long pauses is kept, however short."""
    keep = s.max_pause / 2

    def snap(t: float) -> float:
        return round(round(t / frame) * frame, 6) if frame else round(t, 4)

    out, cursor = [], piece.start
    for a, b in env.silences(s.silence_db, s.max_pause + 2 * max(s.handle, EDGE_MARGIN)):
        a, b = float(a), float(b)
        if a <= piece.start + s.handle or b >= piece.end - s.handle:
            continue
        out.append(replace(piece, start=cursor, end=snap(a + keep)))
        cursor = snap(b - keep)
    out.append(replace(piece, start=cursor, end=piece.end))
    return [p for p in out if p.duration > 0.02] or [piece]


def finish(cut: RoughCut, sources: dict[str, SourceText], envelopes: dict[str, Envelope],
           s: CutSettings = CutSettings(), frames: dict[str, float] | None = None) -> RoughCut:
    """Refine boundaries and shorten pauses for every piece and blooper.

    frames: source id -> frame length in seconds (cuts are snapped onto that grid inside the silence)."""
    frames = frames or {}
    unsafe: list[str] = []

    def one(p: Piece) -> list[Piece]:
        env = envelopes.get(p.source_id)
        if env is None:
            return [p]
        refined, warn = refine(p, sources[p.source_id], env, s, frames.get(p.source_id))
        unsafe.extend(warn)
        return shorten_pauses(refined, env, s, frames.get(p.source_id))

    pieces: list[Piece] = []
    index_map: dict[int, int] = {}
    originals = list(cut.pieces)
    for i, p in enumerate(originals):
        parts = one(p)
        prev = originals[i - 1] if i else None
        if prev is not None and prev.source_id == p.source_id and abs(prev.end - p.start) < 0.05 and pieces:
            # a through-edit (script piece -> improvisation said right after): keep the exact junction
            pieces[-1] = replace(pieces[-1], end=p.start)
            parts[0] = replace(parts[0], start=p.start)
            unsafe[:] = [w for w in unsafe if f"{p.start:.2f}s" not in w and f"{prev.end:.2f}s" not in w]
        elif pieces and pieces[-1].source_id == parts[0].source_id and pieces[-1].start < parts[0].start                 < pieces[-1].end:
            # both boundaries grew over the same words to reach a pause: play the audio once, as one through-edit
            parts[0] = replace(parts[0], start=pieces[-1].end)
        pieces += parts
        index_map[i] = len(pieces) - 1
    markers = tuple(replace(m, after_piece=index_map.get(m.after_piece, m.after_piece)) for m in cut.markers)
    bloopers = tuple(q for p in cut.bloopers for q in one(p))
    return replace(cut, pieces=tuple(pieces), markers=markers, bloopers=bloopers, unsafe_cuts=tuple(unsafe))
