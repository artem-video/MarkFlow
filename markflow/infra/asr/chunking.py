"""Long audio -> short chunks cut at quiet points; token stamps -> words. numpy only, no model.

Transformer/RNNT models (GigaAM, Parakeet) must not get 30 minutes at once (CLAUDE.md pitfalls).
Ported from tools/bench_asr.py (stage 0.4), with a bounded word end.
"""

from __future__ import annotations

import numpy as np

from markflow.domain.transcript import Word

MAX_WORD_TAIL = 0.25  # s after the last token start: models give token starts only


def split_points(samples: np.ndarray, rate: int, max_len: float = 20.0, min_len: float = 8.0,
                 win_s: float = 0.05) -> list[int]:
    """Chunk boundaries (sample indices, first 0, last len) at the quietest window inside [min_len, max_len]."""
    win = max(1, int(win_s * rate))
    n = len(samples)
    cuts, pos = [0], 0
    while n - pos > max_len * rate:
        a, b = pos + int(min_len * rate), pos + int(max_len * rate)
        seg = np.abs(samples[a:b]).astype(np.float32)
        k = (len(seg) // win) * win
        energy = seg[:k].reshape(-1, win).mean(axis=1)
        pos = a + int(energy.argmin()) * win + win // 2
        cuts.append(pos)
    cuts.append(n)
    return cuts


def tokens_to_words(tokens: list[str], starts: list[float], chunk_end: float, offset: float = 0.0,
                    engine: str = "") -> list[Word]:
    """SentencePiece-style tokens ('▁' or ' ' opens a word) with start times -> words in source time."""
    groups: list[list] = []  # [text, first token start, last token start]
    for tok, t in zip(tokens, starts):
        opens = tok.startswith(("▁", " ")) or not groups
        piece = tok.lstrip("▁ ")
        if opens:
            groups.append([piece, t, t])
        else:
            groups[-1][0] += piece
            groups[-1][2] = t
    words = []
    for i, (text, start, last) in enumerate(groups):
        if not text.strip():
            continue
        nxt = groups[i + 1][1] if i + 1 < len(groups) else chunk_end
        end = min(nxt, last + MAX_WORD_TAIL, chunk_end)
        words.append(Word(text.strip(), offset + start, offset + max(end, start), engine))
    return words
