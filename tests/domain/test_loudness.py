from pathlib import Path

import numpy as np
import pytest

from markflow.domain.loudness import FLOOR_DB, Envelope, envelope_from_samples
from markflow.infra.media.loudness import wav_envelope

AUDIO = Path(__file__).resolve().parents[1] / "fixtures" / "audio"
RATE = 16_000


def _signal():
    """1 s silence, 1 s tone at -20 dBFS RMS, 0.5 s silence, 0.5 s tone."""
    t = np.arange(RATE) / RATE
    tone = np.sin(2 * np.pi * 440 * t) * (10 ** (-20 / 20) * np.sqrt(2))
    return np.concatenate([np.zeros(RATE), tone, np.zeros(RATE // 2), tone[: RATE // 2]]).astype(np.float32)


def test_levels_of_a_known_signal():
    env = envelope_from_samples(_signal(), RATE)
    assert env.duration == pytest.approx(3.0)
    assert env.level(1.1, 1.9) == pytest.approx(-20, abs=0.2)
    assert env.level(0.0, 0.9) == FLOOR_DB
    assert env.at(2.2) == FLOOR_DB


def test_silences_and_quietest_point():
    env = envelope_from_samples(_signal(), RATE)
    runs = env.silences(-60, 0.3)
    assert [(round(a, 2), round(b, 2)) for a, b in runs] == [(0.0, 1.0), (2.0, 2.5)]
    assert env.silences(-60, 0.8) == [(0.0, 1.0)]
    assert 2.0 <= env.quietest(1.5, 2.8) <= 2.5


def test_round_trip_keeps_one_decimal():
    env = envelope_from_samples(_signal(), RATE)
    again = Envelope.from_dict(env.to_dict())
    assert np.allclose(again.db, env.db, atol=0.06)
    assert again.hop == env.hop


def test_empty_audio():
    assert envelope_from_samples(np.zeros(10, np.float32), RATE).duration == 0


def test_real_fixture_gap_is_quieter_than_speech():
    """kv_0000s: on-set commands at ~2-4 s, silence ~4.5-8 s, then the host at ~15 s."""
    env = wav_envelope(AUDIO / "kv_0000s_commands_and_intro_take1.wav")
    assert env.duration == pytest.approx(30.0, abs=0.02)
    assert env.level(15.5, 17.0) > env.level(4.5, 8.0) + 10
