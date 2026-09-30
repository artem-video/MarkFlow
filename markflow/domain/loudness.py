"""Loudness envelope of a source: where speech is, where it is quiet enough to cut. Pure (numpy only).

Whisper-like word timings drift at silence edges (CLAUDE.md pitfalls), so every cut is refined on this envelope.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

FLOOR_DB = -100.0
NOISE_MARGIN_DB = 6.0   # silence = this far above the quietest 5 % of the source (room tone of a noisy source)


def silence_threshold(db: np.ndarray, base_db: float) -> float:
    """Silence level of one source: the profile's threshold, raised for sources whose room tone sits above it
    (a studio voice-over at -57 dB can never reach -60). Quiet sources keep the profile value."""
    if len(db) == 0:
        return base_db
    return max(base_db, float(np.percentile(db, 5)) + NOISE_MARGIN_DB)


@dataclass(frozen=True, eq=False)
class Envelope:
    hop: float          # seconds per value
    db: np.ndarray      # RMS level per hop in dBFS, >= FLOOR_DB

    @property
    def duration(self) -> float:
        return len(self.db) * self.hop

    def _slice(self, start: float, end: float) -> tuple[int, int]:
        i = max(0, int(np.floor(start / self.hop)))
        j = min(len(self.db), max(i + 1, int(np.ceil(end / self.hop))))
        return i, j

    def level(self, start: float, end: float) -> float:
        """Loudest value in [start, end)."""
        i, j = self._slice(start, end)
        return float(self.db[i:j].max()) if j > i else FLOOR_DB

    def at(self, t: float) -> float:
        return self.level(t, t + self.hop)

    def quietest(self, start: float, end: float) -> float:
        """Centre time of the quietest hop in [start, end)."""
        i, j = self._slice(start, end)
        k = i + int(np.argmin(self.db[i:j]))
        return (k + 0.5) * self.hop

    def silences(self, threshold_db: float, min_len: float) -> list[tuple[float, float]]:
        """Runs below threshold_db lasting at least min_len seconds."""
        quiet = np.concatenate(([False], self.db < threshold_db, [False]))
        edges = np.flatnonzero(np.diff(quiet.astype(np.int8)))
        runs = [(a * self.hop, b * self.hop) for a, b in zip(edges[0::2], edges[1::2])]
        return [(a, b) for a, b in runs if b - a >= min_len - 1e-9]

    def to_dict(self) -> dict:
        return {"hop": self.hop, "db": [round(float(x), 1) for x in self.db]}

    @staticmethod
    def from_dict(data: dict) -> "Envelope":
        return Envelope(float(data["hop"]), np.asarray(data["db"], dtype=np.float32))


def envelope_from_samples(samples: np.ndarray, sample_rate: int, hop: float = 0.01) -> Envelope:
    """samples: mono float in [-1, 1]."""
    size = max(1, int(round(hop * sample_rate)))
    n = len(samples) // size
    if n == 0:
        return Envelope(hop, np.full(0, FLOOR_DB, dtype=np.float32))
    frames = np.asarray(samples[: n * size], dtype=np.float64).reshape(n, size)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    db = 20 * np.log10(np.maximum(rms, 10 ** (FLOOR_DB / 20)))
    return Envelope(size / sample_rate, db.astype(np.float32))
