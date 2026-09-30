"""Exact in/out points of the lives (PLAN 4.3): transcribe only the window around every timecode."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Callable

from markflow.application.ports import AsrEngine, AsrEngineFactory
from markflow.domain.lives_rules import LiveWindow, refine_window
from markflow.domain.loudness import envelope_from_samples
from markflow.domain.script_model import BlockKind, Script
from markflow.domain.timeline import LIVE_DEFAULT_S, LIVE_MAX_S
from markflow.domain.triage_rules import SourceMeta

WINDOW_S = 5.0     # profile: lives.refine_window_s


def windows_of(script: Script, metas: dict[str, SourceMeta], key_of: Callable[[str], str]
               ) -> dict[str, list[LiveWindow]]:
    """block id -> the timecode windows of a live block whose link was downloaded (as written in the script)."""
    out: dict[str, list[LiveWindow]] = {}
    for b in script.blocks:
        if b.kind not in (BlockKind.LIVE, BlockKind.QUOTE, BlockKind.BUTT) or not b.links:
            continue
        meta = metas.get(key_of(b.links[0]))
        if meta is None:
            continue
        wins = []
        for c in b.clocks:
            end = c.end if c.end is not None and 0 < c.end - c.start <= LIVE_MAX_S else c.start + LIVE_DEFAULT_S
            if c.start < meta.duration:
                wins.append(LiveWindow(c.start, min(end, meta.duration), c.start_words, c.end_words))
        if wins:
            out[b.id] = wins
    return out


class LiveRefiner:
    def __init__(self, audio, asr: AsrEngineFactory, silence_db: float = -60.0, handle: float = 0.04,
                 window_s: float = WINDOW_S, log: Callable[[str], None] = lambda _m: None):
        self.audio, self.factory = audio, asr
        self.silence_db, self.handle, self.window_s, self.log = silence_db, handle, window_s, log
        self._engine: AsrEngine | None = None

    def _asr(self) -> AsrEngine:
        if self._engine is None:
            self._engine = self.factory.load()
        return self._engine

    def close(self) -> None:
        if self._engine is not None:
            self._engine.close()
            self._engine = None

    def refine(self, meta: SourceMeta, win: LiveWindow) -> tuple[float, float]:
        """(start, end) in the file; the script's timecode when nothing can be checked."""
        lo = max(0.0, win.start - self.window_s)
        dur = (win.end + self.window_s) - lo
        key = hashlib.sha1(f"{meta.path}|{lo:.2f}|{dur:.2f}".encode("utf-8")).hexdigest()[:20]
        try:
            wav = self.audio.extract_window(Path(meta.path), lo, dur, key)
            samples, rate = self.audio.read(wav)
            words = [replace(w, start=w.start + lo, end=w.end + lo) for w in self._asr().transcribe(wav)]
        except Exception as e:  # noqa: BLE001 - one bad window must not stop the draft: keep the script's timecode
            self.log(f"live window {meta.id} {win.start:.0f}s: {e}")
            return win.start, win.end
        env = envelope_from_samples(samples, rate)
        return refine_window(win, words, env, lo, self.silence_db, self.handle)

    def refine_all(self, wins: dict[str, list[LiveWindow]], meta_of_block: dict[str, SourceMeta]
                   ) -> dict[str, list[tuple[float, float]]]:
        """block id -> refined (start, end) per timecode; the ASR model is loaded once and released at the end."""
        out = {}
        try:
            for n, (block_id, ws) in enumerate(wins.items(), 1):
                out[block_id] = [self.refine(meta_of_block[block_id], w) for w in ws]
                if n % 25 == 0:
                    self.log(f"lives refined: {n}/{len(wins)}")
        finally:
            self.close()
        return out
