from pathlib import Path

import numpy as np

from markflow.application.transcribe import TranscribeEpisode
from markflow.domain.transcript import Word

RATE = 16_000


class FakeAudio:
    def __init__(self):
        self.extracted = []

    def extract(self, source, fingerprint):
        self.extracted.append(source.name)
        return Path(f"/cache/{fingerprint}.wav")

    def read(self, wav):
        x = np.zeros(RATE * 10, np.float32)
        x[RATE * 2: RATE * 4] = 0.1
        return x, RATE


class FakeEngine:
    def __init__(self, name, words, log):
        self.name, self._words, self._log = name, words, log

    def transcribe(self, wav):
        self._log.append(f"{self.name} {wav.name}")
        return list(reversed(self._words))  # engines may return any order

    def close(self):
        self._log.append(f"{self.name} close")


class FakeFactory:
    def __init__(self, name, words, log):
        self.name, self._words, self._log = name, words, log

    def load(self):
        self._log.append(f"{self.name} load")
        return FakeEngine(self.name, self._words, self._log)


class DictStore(dict):
    def put(self, key, value):
        self[key] = value


def _setup():
    log = []
    giga = FakeFactory("gigaam-v3", [Word("давай", 2.0, 2.5), Word("ещё", 2.6, 3.0)], log)
    para = FakeFactory("parakeet-v3", [Word("давай", 2.0, 2.5), Word("сань", 6.0, 6.4)], log)
    return log, giga, para


def test_one_model_at_a_time_and_merge():
    log, giga, para = _setup()
    audio, store = FakeAudio(), DictStore()
    uc = TranscribeEpisode(audio, [giga, para], store, fingerprint=lambda p: "fp-" + p.stem)
    res = uc.run([Path("B0001.MP4"), Path("Keyed.mov")])
    assert log == ["gigaam-v3 load", "gigaam-v3 fp-B0001.wav", "gigaam-v3 fp-Keyed.wav", "gigaam-v3 close",
                   "parakeet-v3 load", "parakeet-v3 fp-B0001.wav", "parakeet-v3 fp-Keyed.wav", "parakeet-v3 close"]
    assert audio.extracted == ["B0001.MP4", "Keyed.mov"]  # each source extracted once
    r = res[0]
    assert [w.text for w in r.merged.words] == ["давай", "ещё", "сань"]
    assert r.transcripts["gigaam-v3"].duration == 10.0
    assert r.envelope.level(2.5, 3.5) > r.envelope.level(6, 8)


def test_second_run_uses_cache_only():
    log, giga, para = _setup()
    store = DictStore()
    TranscribeEpisode(FakeAudio(), [giga, para], store, fingerprint=lambda p: "fp").run([Path("a.mov")])
    log.clear()
    audio = FakeAudio()
    res = TranscribeEpisode(audio, [giga, para], store, fingerprint=lambda p: "fp").run([Path("a.mov")])
    assert log == [] and audio.extracted == []
    assert len(res[0].merged.words) == 3


def test_engine_is_closed_even_on_error():
    log = []

    class Boom(FakeEngine):
        def transcribe(self, wav):
            raise RuntimeError("GPU out of memory")

    class BoomFactory(FakeFactory):
        def load(self):
            return Boom(self.name, [], self._log)

    uc = TranscribeEpisode(FakeAudio(), [BoomFactory("gigaam-v3", [], log)], DictStore(), fingerprint=lambda p: "fp")
    try:
        uc.run([Path("a.mov")])
    except RuntimeError:
        pass
    assert log == ["gigaam-v3 close"]


def test_pc_tool_report_and_dump(tmp_path):
    from tools.transcribe_episode import dump, report

    log, giga, para = _setup()
    res = TranscribeEpisode(FakeAudio(), [giga, para], DictStore(), fingerprint=lambda p: "fp").run([Path("kv.wav")])
    text = report(res, 90)
    assert "| kv.wav | 0.2 min | 2 | 2 | 3 |" in text
    dump(res, tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "kv.gigaam-v3.json", "kv.merged.json", "kv.parakeet-v3.json"]
