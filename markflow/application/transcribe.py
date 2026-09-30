"""Stage 2.1 use case: every source of an episode -> word transcript (per engine + merged) + loudness envelope.

Engines run one after another over all sources (one model in GPU memory at a time). Everything is cached
by the source fingerprint, so a second run only does what is missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from markflow.application.ports import AsrEngineFactory, Audio, Fingerprinter, JsonStore
from markflow.domain.loudness import Envelope, envelope_from_samples
from markflow.domain.transcript import Transcript, merge_fill_gaps

Log = Callable[[str], None]


@dataclass(frozen=True)
class SourceAudioData:
    source: Path
    fingerprint: str
    transcripts: dict[str, Transcript]  # engine name -> transcript
    merged: Transcript
    envelope: Envelope


class TranscribeEpisode:
    def __init__(self, audio: Audio, engines: list[AsrEngineFactory], store: JsonStore,
                 fingerprint: Fingerprinter, log: Log = lambda _: None):
        if not engines:
            raise ValueError("at least one ASR engine is needed")
        self._audio, self._engines, self._store, self._fp, self._log = audio, engines, store, fingerprint, log

    @staticmethod
    def transcript_key(fp: str, engine: str) -> str:
        return f"transcript/{engine}/{fp}"

    @staticmethod
    def envelope_key(fp: str) -> str:
        return f"envelope/{fp}"

    def run(self, sources: list[Path]) -> list[SourceAudioData]:
        prints = {src: self._fp(src) for src in sources}
        wavs: dict[Path, Path] = {}

        def wav(src: Path) -> Path:
            if src not in wavs:
                self._log(f"audio: {src.name}")
                wavs[src] = self._audio.extract(src, prints[src])
            return wavs[src]

        durations: dict[Path, float] = {}
        for src in sources:
            key = self.envelope_key(prints[src])
            cached = self._store.get(key)
            if cached is None:
                samples, rate = self._audio.read(wav(src))
                env = envelope_from_samples(samples, rate)
                self._store.put(key, env.to_dict())
            else:
                env = Envelope.from_dict(cached)
            durations[src] = env.duration

        for factory in self._engines:
            todo = [s for s in sources if self._store.get(self.transcript_key(prints[s], factory.name)) is None]
            if not todo:
                continue
            self._log(f"{factory.name}: loading model")
            engine = factory.load()
            try:
                for src in todo:
                    self._log(f"{factory.name}: {src.name}")
                    words = sorted(engine.transcribe(wav(src)), key=lambda w: (w.start, w.end))
                    t = Transcript(src.name, factory.name, durations[src], tuple(words))
                    self._store.put(self.transcript_key(prints[src], factory.name), t.to_dict())
            finally:
                engine.close()

        results = []
        for src in sources:
            fp = prints[src]
            per = {f.name: Transcript.from_dict(self._store.get(self.transcript_key(fp, f.name)))
                   for f in self._engines}
            merged = per[self._engines[0].name]
            for f in self._engines[1:]:
                merged = merge_fill_gaps(merged, per[f.name])
            env = Envelope.from_dict(self._store.get(self.envelope_key(fp)))
            results.append(SourceAudioData(src, fp, per, merged, env))
        return results
