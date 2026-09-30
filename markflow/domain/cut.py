"""Rough cut (stages 2.3–2.4): chosen takes -> ordered speech pieces with clean boundaries. Pure.

- consecutive sentences taken from one continuous stretch of a recording become one piece;
- what was said between them is classified: command (cut, marker), improvisation (kept, coloured), junk (cut);
- improvisation that is not between two chosen takes goes to a bloopers tail (never silently removed);
- every boundary is moved into silence on the loudness envelope (never cut a live word), keeping a handle;
- long pauses inside a piece are shortened to the profile maximum (Phantom-style).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from markflow.domain.align import Alignment, Choice, Occurrence, SourceText
from markflow.domain.commands import OffScript, OffScriptRules, classify
from markflow.domain.loudness import Envelope
from markflow.shared.text_norm import normalize

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


def _collapse_repeats(words: list[str]) -> list[str]:
    """'если вдруг если вдруг меня' -> 'если вдруг меня' (stutters and restarts)."""
    out = list(words)
    changed = True
    while changed:
        changed = False
        for n in (3, 2, 1):
            i = 0
            while i + 2 * n <= len(out):
                if out[i:i + n] == out[i + n:i + 2 * n]:
                    del out[i + n:i + 2 * n]
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

    def kind_of(text: str) -> OffScript:
        kind = classify(text, rules)
        if kind == OffScript.COMMAND:
            return kind
        if written.is_failed_take(text):
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
            kind = kind_of(_text(src, x, y))
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

def _neighbour_bounds(src: SourceText, start: float, end: float) -> tuple[float, float]:
    """End of the last word before `start`, start of the first word after `end` (other speech)."""
    before = [t.end for t in src.tokens if t.end <= start + 1e-6]
    after = [t.start for t in src.tokens if t.start >= end - 1e-6]
    return (max(before) if before else 0.0), (min(after) if after else float("inf"))


def _silent_edge(env: Envelope, lo: float, hi: float, threshold: float, leftwards: bool) -> float | None:
    """Nearest point to the speech side of [lo, hi] where the level drops under threshold."""
    hop = env.hop
    if hi - lo < hop:
        return None
    steps = int((hi - lo) / hop)
    order = range(steps - 1, -1, -1) if leftwards else range(steps)
    for k in order:
        t = lo + k * hop
        if env.level(t, t + hop) < threshold:
            return t + (hop if leftwards else 0.0)
    return None


def _onset(env: Envelope, lo: float, hi: float, threshold: float) -> float | None:
    """First moment in [lo, hi) where the level rises to the threshold (speech starts)."""
    t = lo
    while t < hi:
        if env.level(t, t + env.hop) >= threshold:
            return t
        t += env.hop
    return None


def _offset(env: Envelope, lo: float, hi: float, threshold: float) -> float | None:
    """Last moment in (lo, hi] where the level is at the threshold (speech ends)."""
    t = hi - env.hop
    while t >= lo:
        if env.level(t, t + env.hop) >= threshold:
            return t + env.hop
        t -= env.hop
    return None


def refine(piece: Piece, src: SourceText, env: Envelope, s: CutSettings) -> tuple[Piece, list[str]]:
    """Put both ends at the real speech edges on the envelope, plus the handle, never into other speech.

    ASR word times drift at silence edges: when the word 'starts' in silence, move forward to the real onset;
    when it starts inside sound, move back to the nearest silence.
    """
    warnings = []
    thr = s.silence_db
    prev_end, next_start = _neighbour_bounds(src, piece.start, piece.end)
    lo = max(prev_end, piece.start - s.search, 0.0)
    hi = min(next_start, piece.end + s.search, env.duration)

    if env.level(piece.start, piece.start + env.hop) < thr:
        onset = _onset(env, piece.start, min(piece.end, piece.start + 2 * s.search + 0.5), thr)
        edge = onset if onset is not None else piece.start
    else:
        edge = _silent_edge(env, lo, piece.start, thr, leftwards=True)
        if edge is None:
            edge = env.quietest(lo, piece.start + env.hop) if piece.start - lo >= env.hop else piece.start
            if env.level(edge - env.hop, edge + env.hop) >= thr:
                warnings.append(f"{piece.source_id} {piece.start:.2f}s: начало реза не в тишине")
    start = max(lo, edge - s.handle)

    if env.level(piece.end - env.hop, piece.end) < thr:
        off = _offset(env, max(start, piece.end - 2 * s.search - 0.5), piece.end, thr)
        edge = off if off is not None else piece.end
    else:
        edge = _silent_edge(env, piece.end, hi, thr, leftwards=False)
        if edge is None:
            edge = env.quietest(piece.end, hi) if hi - piece.end >= env.hop else piece.end
            if env.level(edge - env.hop, edge + env.hop) >= thr:
                warnings.append(f"{piece.source_id} {piece.end:.2f}s: конец реза не в тишине")
    end = min(hi, edge + s.handle)
    return replace(piece, start=round(start, 4), end=round(max(end, start + s.min_piece), 4)), warnings


def shorten_pauses(piece: Piece, env: Envelope, s: CutSettings) -> list[Piece]:
    """Split a piece at silences longer than max_pause, leaving max_pause of the pause (half on each side)."""
    keep = s.max_pause / 2
    out, cursor = [], piece.start
    for a, b in env.silences(s.silence_db, s.max_pause + 2 * s.handle):
        a, b = float(a), float(b)
        if a <= piece.start + s.handle or b >= piece.end - s.handle:
            continue
        out.append(replace(piece, start=cursor, end=round(a + keep, 4)))
        cursor = round(b - keep, 4)
    out.append(replace(piece, start=cursor, end=piece.end))
    return [p for p in out if p.duration >= s.min_piece] or [piece]


def finish(cut: RoughCut, sources: dict[str, SourceText], envelopes: dict[str, Envelope],
           s: CutSettings = CutSettings()) -> RoughCut:
    """Refine boundaries and shorten pauses for every piece and blooper."""
    unsafe: list[str] = []

    def one(p: Piece) -> list[Piece]:
        env = envelopes.get(p.source_id)
        if env is None:
            return [p]
        refined, warn = refine(p, sources[p.source_id], env, s)
        unsafe.extend(warn)
        return shorten_pauses(refined, env, s)

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
        pieces += parts
        index_map[i] = len(pieces) - 1
    markers = tuple(replace(m, after_piece=index_map.get(m.after_piece, m.after_piece)) for m in cut.markers)
    bloopers = tuple(q for p in cut.bloopers for q in one(p))
    return replace(cut, pieces=tuple(pieces), markers=markers, bloopers=bloopers, unsafe_cuts=tuple(unsafe))
