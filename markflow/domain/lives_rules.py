"""Where exactly a live starts and ends (PLAN 4.3). Pure: words and loudness in, seconds out.

The script gives a timecode written by a human, often a second or two off, and sometimes the words said there
('16:06 государство — 16:28 действия'). The window around the timecode is transcribed, the words are found in it,
and the cut goes into the nearest pause: a live never starts or ends in the middle of a word.
"""

from __future__ import annotations

from dataclasses import dataclass

from markflow.domain.align import word_sim
from markflow.domain.loudness import Envelope
from markflow.domain.transcript import Word
from markflow.shared.text_norm import normalize

PHRASE_WORDS = 4   # how many words at the edge of the quoted phrase are matched
MATCH_SIM = 0.8


@dataclass(frozen=True)
class LiveWindow:
    start: float          # seconds in the live's file
    end: float
    start_words: str = ""
    end_words: str = ""


def _find(words: list[str], phrase: list[str], near: float, times: list[float]) -> int | None:
    """Index of the match of `phrase` whose time is nearest to `near` (None when not found)."""
    best, best_d = None, 1e9
    for i in range(len(words) - len(phrase) + 1):
        if all(word_sim(words[i + k], phrase[k]) >= MATCH_SIM for k in range(len(phrase))):
            d = abs(times[i] - near)
            if d < best_d:
                best, best_d = i, d
    return best


def locate_start(words: list[Word], spoken: str, near: float) -> float | None:
    """Start time of the first word of `spoken` (its first words) nearest to `near`."""
    phrase = normalize(spoken).split()[:PHRASE_WORDS]
    if not phrase:
        return None
    w = [normalize(x.text) for x in words]
    i = _find(w, phrase, near, [x.start for x in words])
    return None if i is None else words[i].start


def locate_end(words: list[Word], spoken: str, near: float) -> float | None:
    """End time of the last word of `spoken` (its last words) nearest to `near`."""
    phrase = normalize(spoken).split()[-PHRASE_WORDS:]
    if not phrase:
        return None
    w = [normalize(x.text) for x in words]
    i = _find(w, phrase, near, [x.end for x in words])
    return None if i is None else words[i + len(phrase) - 1].end


def snap_to_pause(env: Envelope, t: float, is_start: bool, threshold: float, handle: float,
                  search: float = 0.4) -> float:
    """The cut goes into the pause next to t: `handle` before the sound that follows it (a start) or `handle`
    after the sound that precedes it (an end). No pause within `search` seconds: t stays."""
    runs = [(a, b) for a, b in env.silences(threshold, 0.05) if b >= t - search and a <= t + search]
    if not runs:
        return t
    if is_start:
        a, b = min(runs, key=lambda r: abs(r[1] - t))
        return max(a, b - handle)
    a, b = min(runs, key=lambda r: abs(r[0] - t))
    return min(b, a + handle)


def refine_window(win: LiveWindow, words: list[Word], env: Envelope, env_offset: float, threshold: float,
                  handle: float) -> tuple[float, float]:
    """(start, end) in the live's file. `words` carry file times, `env` starts at `env_offset` of the file."""
    a = locate_start(words, win.start_words, win.start) if win.start_words else None
    b = locate_end(words, win.end_words, win.end) if win.end_words else None
    a = win.start if a is None else a
    b = win.end if b is None else b
    a = snap_to_pause(env, a - env_offset, True, threshold, handle) + env_offset
    b = snap_to_pause(env, b - env_offset, False, threshold, handle) + env_offset
    return (max(0.0, a), max(a + 0.3, b))
