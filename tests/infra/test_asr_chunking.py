import numpy as np
import pytest

from markflow.infra.asr.chunking import MAX_WORD_TAIL, split_points, tokens_to_words
from markflow.infra.asr.onnx_engine import AsrError, OnnxAsrFactory
from markflow.infra.media.ffmpeg import FfmpegAudio

RATE = 16_000


def test_split_points_cut_in_quiet_places():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 0.3, RATE * 50).astype(np.float32)
    for q in (15, 33):  # two quiet 0.3 s holes
        x[q * RATE: q * RATE + int(0.3 * RATE)] = 0
    cuts = split_points(x, RATE)
    assert cuts[0] == 0 and cuts[-1] == len(x)
    assert all(8 * RATE <= b - a <= 20 * RATE for a, b in zip(cuts, cuts[1:-1]))
    assert any(abs(c / RATE - 15.15) < 0.2 for c in cuts) and any(abs(c / RATE - 33.15) < 0.2 for c in cuts)


def test_short_audio_is_one_chunk():
    assert split_points(np.zeros(RATE * 5, np.float32), RATE) == [0, RATE * 5]


def test_tokens_to_words():
    tokens = ["▁при", "вет", "▁мир", "▁", "▁да"]
    starts = [0.1, 0.3, 0.8, 1.0, 3.0]
    words = tokens_to_words(tokens, starts, chunk_end=5.0, offset=100.0, engine="gigaam-v3")
    assert [(w.text, w.start) for w in words] == [("привет", 100.1), ("мир", 100.8), ("да", 103.0)]
    assert words[0].end == pytest.approx(100.55)                # last token 0.3 + tail, before next word
    assert words[2].end == pytest.approx(103.0 + MAX_WORD_TAIL)  # not stretched to the chunk end


class _Result:
    def __init__(self, tokens, stamps):
        self.tokens, self.timestamps = tokens, stamps


class _FakeModel:
    def __init__(self):
        self.chunks = []

    def recognize(self, x, sample_rate):
        self.chunks.append(len(x) / sample_rate)
        return _Result(["▁раз"], [0.5]) if len(self.chunks) == 1 else _Result(None, None)


def test_engine_runs_chunks_and_offsets(tmp_path):
    import wave

    wav = tmp_path / "a.wav"
    data = (np.random.default_rng(1).normal(0, 0.2, RATE * 30) * 32767).astype("<i2")
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(RATE), w.writeframes(data.tobytes())
    model = _FakeModel()
    engine = OnnxAsrFactory("gigaam-v3", loader=lambda mid, cpu: model).load()
    words = engine.transcribe(wav)
    assert len(model.chunks) == 2 and sum(model.chunks) == pytest.approx(30)
    assert [(w.text, w.engine) for w in words] == [("раз", "gigaam-v3")]
    engine.close()
    with pytest.raises(AsrError, match="closed"):
        engine.transcribe(wav)


def test_factory_knows_only_chosen_models():
    assert OnnxAsrFactory("parakeet-v3", loader=lambda mid, cpu: mid).load()._model == "nemo-parakeet-tdt-0.6b-v3"
    with pytest.raises(AsrError, match="unknown"):
        OnnxAsrFactory("whisper-turbo")


def test_wav_reader_rejects_stereo(tmp_path):
    import wave

    wav = tmp_path / "st.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2), w.setsampwidth(2), w.setframerate(RATE), w.writeframes(b"\0\0\0\0" * 10)
    with pytest.raises(Exception, match="mono"):
        FfmpegAudio(tmp_path).read(wav)
