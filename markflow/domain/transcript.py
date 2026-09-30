"""Word-level transcript of one source, and merging two ASR engines. Pure.

Stage 0.4 choice (docs/PLAN.md §5.12): GigaAM v3 sees the most retakes (it keeps half-said phrases that other
models drop), Parakeet-v3 has the best text and is the fastest. The merge keeps GigaAM as the timeline of
what was said and fills its holes with Parakeet words, so no retake is lost and no stretch of speech is empty.
Both raw transcripts stay in the cache: alignment (2.3) can compare them where they disagree.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Word:
    text: str
    start: float  # seconds in the source
    end: float
    engine: str = ""

    def to_list(self) -> list:
        return [self.text, round(self.start, 3), round(self.end, 3), self.engine]

    @staticmethod
    def from_list(row: list) -> "Word":
        return Word(row[0], float(row[1]), float(row[2]), row[3] if len(row) > 3 else "")


@dataclass(frozen=True)
class Transcript:
    source_id: str
    engine: str
    duration: float
    words: tuple[Word, ...] = field(default=())

    def __post_init__(self) -> None:
        for a, b in zip(self.words, self.words[1:]):
            if b.start < a.start:
                raise ValueError(f"{self.engine}: words out of order at {b.start:.2f}s")
        for w in self.words:
            if w.end < w.start:
                raise ValueError(f"{self.engine}: word {w.text!r} ends before it starts")

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    def between(self, start: float, end: float) -> list[Word]:
        return [w for w in self.words if w.start < end and w.end > start]

    def gaps(self, min_gap: float) -> list[tuple[float, float]]:
        """Stretches without words (incl. head and tail) longer than min_gap."""
        edges = [0.0] + [x for w in self.words for x in (w.start, w.end)] + [self.duration]
        out = []
        for a, b in zip(edges[0::2], edges[1::2]):
            if b - a >= min_gap:
                out.append((a, b))
        return out

    def to_dict(self) -> dict:
        return {"source_id": self.source_id, "engine": self.engine, "duration": self.duration,
                "words": [w.to_list() for w in self.words]}

    @staticmethod
    def from_dict(data: dict) -> "Transcript":
        return Transcript(data["source_id"], data["engine"], float(data["duration"]),
                          tuple(Word.from_list(r) for r in data["words"]))


def merge_fill_gaps(primary: Transcript, secondary: Transcript, min_gap: float = 0.4,
                    margin: float = 0.05) -> Transcript:
    """Primary words everywhere; secondary words only where the primary heard nothing."""
    if primary.source_id != secondary.source_id:
        raise ValueError("cannot merge transcripts of different sources")
    holes = primary.gaps(min_gap)
    extra = [
        w for w in secondary.words
        if any(a + margin <= w.start and w.end <= b - margin for a, b in holes)
    ]
    tag = lambda t: tuple(w if w.engine else Word(w.text, w.start, w.end, t.engine) for w in t.words)  # noqa: E731
    words = sorted(tag(primary) + tuple(w if w.engine else Word(w.text, w.start, w.end, secondary.engine)
                                        for w in extra), key=lambda w: (w.start, w.end))
    return Transcript(primary.source_id, f"{primary.engine}+{secondary.engine}",
                      max(primary.duration, secondary.duration), tuple(words))
