"""Script <-> transcript alignment and take choice (stage 2.3). Pure.

The script is split into units (sentences, ≥ 4 words). Each unit is searched in every transcript:
candidate positions come from word votes, then a local word alignment (Smith-Waterman with fuzzy word
equality) measures how much of the unit a stretch of speech covers. Every stretch with enough coverage is
an *occurrence* (a take, maybe partial). Rules (CLAUDE.md): script beats transcript; a re-recorded phrase
= the last complete take in recording order.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache

from rapidfuzz import fuzz

from markflow.domain.script_model import BlockKind, Script
from markflow.domain.transcript import Transcript
from markflow.shared.text_norm import normalize

MIN_UNIT_WORDS = 4
MIN_COVERAGE = 0.5       # a stretch covering less than half of a sentence is not a take of it
COMPLETE_COVERAGE = 0.75

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[«\"(\[A-ZА-ЯЁ0-9—-])")


@dataclass(frozen=True)
class Unit:
    id: str            # 'B014.2'
    block_id: str
    kind: BlockKind
    text: str
    words: tuple[str, ...]


@dataclass(frozen=True)
class Token:
    word: str          # normalized
    start: float
    end: float
    raw: str


@dataclass(frozen=True)
class SourceText:
    source_id: str
    order: int         # recording order (triage): later = more important
    tokens: tuple[Token, ...]
    audio_only: bool = False

    @staticmethod
    def from_transcript(t: Transcript, order: int, audio_only: bool = False) -> "SourceText":
        toks = []
        for w in t.words:
            for part in normalize(w.text).split():
                toks.append(Token(part, w.start, w.end, w.text))
        return SourceText(t.source_id, order, tuple(toks), audio_only)


@dataclass(frozen=True)
class Occurrence:
    unit_id: str
    source_id: str
    order: int
    first: int         # token indices, inclusive
    last: int
    start: float
    end: float
    coverage: float
    complete: bool

    @property
    def sort_key(self) -> tuple[int, float]:
        return (self.order, self.start)


@dataclass(frozen=True)
class Choice:
    unit: Unit
    chosen: Occurrence | None
    takes: tuple[Occurrence, ...]            # all occurrences, recording order
    checks: tuple[str, ...] = ()

    @property
    def retakes(self) -> int:
        return max(0, len(self.takes) - 1)


@dataclass(frozen=True)
class Alignment:
    choices: tuple[Choice, ...]
    occurrences: dict[str, tuple[Occurrence, ...]] = field(default_factory=dict)  # source -> all, by start

    def found_share(self) -> float:
        return sum(c.chosen is not None for c in self.choices) / max(1, len(self.choices))


# ---------- units ----------

def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_END.split(text) if p.strip()]
    merged: list[str] = []
    for p in parts:
        if merged and len(normalize(merged[-1]).split()) < MIN_UNIT_WORDS:
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)
    if len(merged) > 1 and len(normalize(merged[-1]).split()) < MIN_UNIT_WORDS:
        tail = merged.pop()
        merged[-1] = f"{merged[-1]} {tail}"
    return merged


def script_units(script: Script) -> list[Unit]:
    units = []
    for block in script.spoken_blocks:
        for i, sentence in enumerate(split_sentences(" ".join(block.lines)), 1):
            words = tuple(normalize(sentence).split())
            if words:
                units.append(Unit(f"{block.id}.{i}", block.id, block.kind, sentence, words))
    return units


# ---------- word similarity & local alignment ----------

@lru_cache(maxsize=200_000)
def word_sim(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if min(len(a), len(b)) >= 5 and a[:5] == b[:5]:
        return 0.9  # same stem, different ending: ASR vs script morphology
    if min(len(a), len(b)) <= 2:
        return 0.0
    return fuzz.ratio(a, b) / 100.0


def _local_align(unit: tuple[str, ...], toks: tuple[Token, ...], lo: int, hi: int):
    """Best local alignment of unit words against toks[lo:hi]. -> (score, t_first, t_last, matched unit idx set)."""
    n, m = len(unit), hi - lo
    if m <= 0:
        return 0.0, -1, -1, frozenset()
    prev = [0.0] * (m + 1)
    back: list[list[tuple[int, int, bool] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    best = (0.0, 0, 0)
    for i in range(1, n + 1):
        cur = [0.0] * (m + 1)
        ui = unit[i - 1]
        for j in range(1, m + 1):
            sim = word_sim(ui, toks[lo + j - 1].word)
            diag = prev[j - 1] + (2.0 if sim >= 0.8 else -1.0)
            up = prev[j] - 0.8       # unit word missing in speech
            left = cur[j - 1] - 0.6  # extra spoken word (filler, stutter)
            val = max(0.0, diag, up, left)
            cur[j] = val
            if val == 0.0:
                back[i][j] = None
            elif val == diag:
                back[i][j] = (i - 1, j - 1, sim >= 0.8)
            elif val == up:
                back[i][j] = (i - 1, j, False)
            else:
                back[i][j] = (i, j - 1, False)
            if val > best[0]:
                best = (val, i, j)
        prev = cur
    score, i, j = best
    if score <= 0:
        return 0.0, -1, -1, frozenset()
    matched, t_last, t_first = set(), lo + j - 1, lo + j - 1
    while i > 0 and j > 0 and back[i][j] is not None:
        pi, pj, is_match = back[i][j]
        if is_match:
            matched.add(i - 1)
            t_first = lo + j - 1
        i, j = pi, pj
    return score, t_first, t_last, frozenset(matched)


# ---------- occurrences ----------

class _Index:
    def __init__(self, src: SourceText):
        self.src = src
        self.exact: dict[str, list[int]] = {}
        self.stem: dict[str, list[int]] = {}
        for k, t in enumerate(src.tokens):
            self.exact.setdefault(t.word, []).append(k)
            if len(t.word) >= 5:
                self.stem.setdefault(t.word[:5], []).append(k)

    def candidates(self, unit: tuple[str, ...]) -> list[int]:
        votes: dict[int, set[int]] = {}
        for i, w in enumerate(unit):
            if len(w) <= 2:
                continue  # 'и', 'в', 'не' vote everywhere
            positions = set(self.exact.get(w, ()))
            if len(w) >= 5:
                positions |= set(self.stem.get(w[:5], ()))
            for p in positions:
                votes.setdefault((p - i) // 4, set()).add(i)
        content = sum(1 for w in unit if len(w) > 2) or 1
        need = max(2, math.ceil(0.3 * content)) if content > 2 else content
        buckets = sorted(b for b, who in votes.items() if len(who) >= need)
        return [b * 4 for b in buckets]


def find_occurrences(unit: Unit, index: _Index) -> list[Occurrence]:
    toks = index.src.tokens
    n = len(unit.words)
    windows: list[list[int]] = []
    for start in index.candidates(unit.words):
        lo, hi = max(0, start - 4), min(len(toks), start + int(n * 1.5) + 8)
        if windows and lo <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], hi)
        else:
            windows.append([lo, hi])
    found: list[Occurrence] = []
    for lo, hi in windows:
        # a merged window can hold several takes back to back: peel them off one by one
        while hi - lo >= 1:
            score, a, b, matched = _local_align(unit.words, toks, lo, hi)
            if a < 0:
                break
            coverage = len(matched) / n
            if coverage >= MIN_COVERAGE and len(matched) >= min(3, n):
                head = min(matched) <= max(1, n // 5)
                tail = max(matched) >= n - 1 - max(1, n // 5)
                found.append(Occurrence(unit.id, index.src.source_id, index.src.order, a, b,
                                        toks[a].start, toks[b].end, round(coverage, 3),
                                        coverage >= COMPLETE_COVERAGE and head and tail))
            else:
                break
            left, right = (lo, a), (b + 1, hi)
            if right[1] - right[0] >= max(3, n // 2):
                lo, hi = right
            elif left[1] - left[0] >= max(3, n // 2):
                lo, hi = left
            else:
                break
    return found


# ---------- take choice ----------

LAST_TAKE_BONUS = 1.0   # the rule: the last complete take wins
CONTINUITY_BONUS = 0.4  # tie-breaker: the next sentence follows right after in the same recording
CONTINUITY_GAP = 15.0   # s


def _drop_isolated(units: list[Unit], takes: list[list[Occurrence]]) -> list[list[Occurrence]]:
    """A short or weak match with no neighbouring sentence nearby is a coincidence ('на самом деле нет')."""
    out = []
    for k, unit in enumerate(units):
        kept = []
        for o in takes[k]:
            strong = len(unit.words) >= 8 and o.coverage >= 0.9
            near = any(
                n.source_id == o.source_id and abs(n.start - o.start) <= 90
                for j in range(max(0, k - 2), min(len(units), k + 3)) if j != k
                for n in takes[j]
            ) or any(  # a torn retake right next to a solid take of the same sentence
                n is not o and n.source_id == o.source_id and abs(n.start - o.start) <= 90
                and len(unit.words) >= 8 and n.coverage >= 0.9
                for n in takes[k]
            )
            if strong or near:
                kept.append(o)
        out.append(kept)
    return out


def _quality(o: Occurrence, last_complete: Occurrence | None, rank: float) -> float:
    q = 1.0 if o.complete else o.coverage * 0.8
    return q + (LAST_TAKE_BONUS if o is last_complete else 0.0) + 0.01 * rank  # later wins a tie


def _continues(a: Occurrence, b: Occurrence) -> bool:
    return a.source_id == b.source_id and -1.0 <= b.start - a.end <= CONTINUITY_GAP


def _choose_all(units: list[Unit], takes: list[list[Occurrence]]) -> list[Choice]:
    """Viterbi over sentences: per-take quality (last complete take first) + continuity between neighbours."""
    ordered = [sorted(t, key=lambda o: o.sort_key) for t in takes]
    last_complete = [next((o for o in reversed(t) if o.complete), None) for t in ordered]
    # states per unit: its takes, or a single None when nothing was found
    states = [t if t else [None] for t in ordered]
    score: list[list[float]] = []
    back: list[list[int]] = []
    for k, sts in enumerate(states):
        row, brow = [], []
        for o in sts:
            base = _quality(o, last_complete[k], sts.index(o)) if o is not None else 0.0
            if k == 0:
                row.append(base)
                brow.append(-1)
                continue
            best, arg = -1e9, 0
            for pi, p in enumerate(states[k - 1]):
                val = score[k - 1][pi]
                if p is not None and o is not None and _continues(p, o):
                    val += CONTINUITY_BONUS
                if val > best:
                    best, arg = val, pi
            row.append(best + base)
            brow.append(arg)
        score.append(row)
        back.append(brow)
    picks = [0] * len(states)
    if states:
        picks[-1] = max(range(len(states[-1])), key=lambda i: score[-1][i])
        for k in range(len(states) - 1, 0, -1):
            picks[k - 1] = back[k][picks[k]]
    choices = []
    for k, unit in enumerate(units):
        chosen = states[k][picks[k]]
        checks: list[str] = []
        if chosen is None:
            checks.append("строка сценария не найдена в исходниках")
        elif not chosen.complete:
            checks.append(f"нет полного дубля (лучший покрывает {round(chosen.coverage * 100)} %)")
        elif ordered[k] and ordered[k][-1].sort_key > chosen.sort_key and not ordered[k][-1].complete:
            checks.append("после выбранного дубля есть недоговорённый")
        elif last_complete[k] is not None and chosen is not last_complete[k]:
            checks.append("выбран не последний полный дубль (по связности с соседями)")
        choices.append(Choice(unit, chosen, tuple(ordered[k]), tuple(checks)))
    return choices


def align(units: list[Unit], sources: list[SourceText]) -> Alignment:
    indexes = [_Index(s) for s in sources]
    has_vo = any(s.audio_only for s in sources)
    takes: list[list[Occurrence]] = []
    for unit in units:
        found: list[Occurrence] = []
        if unit.kind == BlockKind.VOICEOVER and has_vo:
            # voiceover text is taken from the VO recording when it is there
            for idx in indexes:
                if idx.src.audio_only:
                    found += find_occurrences(unit, idx)
        if not found:
            for idx in indexes:
                found += find_occurrences(unit, idx)
        takes.append(found)
    takes = _drop_isolated(units, takes)
    all_occ: dict[str, list[Occurrence]] = {s.source_id: [] for s in sources}
    for t in takes:
        for o in t:
            all_occ[o.source_id].append(o)
    return Alignment(tuple(_choose_all(units, takes)),
                     {k: tuple(sorted(v, key=lambda o: o.start)) for k, v in all_occ.items()})
