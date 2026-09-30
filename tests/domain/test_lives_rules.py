import numpy as np

from markflow.domain.lives_rules import LiveWindow, locate_end, locate_start, refine_window, snap_to_pause
from markflow.domain.loudness import Envelope
from markflow.domain.transcript import Word


def _words(text: str, t0: float = 100.0, step: float = 0.4) -> list[Word]:
    return [Word(w, t0 + i * step, t0 + i * step + 0.3) for i, w in enumerate(text.split())]


def _env(loud_ranges: list[tuple[float, float]], total: float, offset: float = 0.0) -> Envelope:
    db = np.full(int(total / 0.01), -80.0, dtype=np.float32)
    for a, b in loud_ranges:
        db[int(round((a - offset) / 0.01)):int(round((b - offset) / 0.01))] = -25.0
    return Envelope(0.01, db)


def test_start_and_end_words_are_found_nearest_to_the_timecode():
    w = _words("ну вот государство а потом государство не хочет действия в итоге")
    assert locate_start(w, "государство не хочет", near=102.0) == w[5].start     # the second 'государство'
    assert locate_end(w, "не хочет действия", near=103.0) == w[8].end
    assert locate_start(w, "совсем другое", near=100.0) is None


def test_cut_goes_into_the_pause_next_to_the_word():
    env = _env([(0.0, 0.9), (1.2, 2.0)], total=4.0)          # a pause 0.9-1.2
    assert abs(snap_to_pause(env, 1.25, True, threshold=-60.0, handle=0.04) - 1.16) < 0.02   # just before the sound
    assert abs(snap_to_pause(env, 0.95, False, threshold=-60.0, handle=0.04) - 0.94) < 0.02  # just after the sound
    loud = _env([(0.0, 4.0)], total=4.0)                                                     # no pause at all
    assert snap_to_pause(loud, 2.0, True, threshold=-60.0, handle=0.04) == 2.0


def test_refine_window_moves_a_sloppy_timecode_onto_the_spoken_words():
    words = _words("раз два три четыре пять шесть", t0=50.0, step=0.5)      # 'три' 51.0-51.3, 'пять' ends 52.3
    env = _env([(50.0 + 0.5 * i, 50.3 + 0.5 * i) for i in range(6)], total=4.0, offset=50.0)
    win = LiveWindow(start=50.4, end=52.6, start_words="три четыре", end_words="четыре пять")
    a, b = refine_window(win, words, env, 50.0, -60.0, 0.04)
    assert abs(a - 50.96) < 0.03 and abs(b - 52.34) < 0.03
