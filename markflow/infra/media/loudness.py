"""Loudness envelope straight from a WAV file (the math is in domain/loudness.py)."""

from __future__ import annotations

from pathlib import Path

from markflow.domain.loudness import Envelope, envelope_from_samples
from markflow.infra.media.ffmpeg import FfmpegAudio


def wav_envelope(wav: Path, hop: float = 0.01) -> Envelope:
    samples, rate = FfmpegAudio(Path(".")).read(wav)
    return envelope_from_samples(samples, rate, hop)
