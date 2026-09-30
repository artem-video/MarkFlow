import subprocess
from pathlib import Path

import pytest

from markflow.infra.cache import JsonFileStore, fast_fingerprint
from markflow.infra.media.ffmpeg import FfmpegAudio, MediaError, find_tool, parse_probe

PROBE_KEYED = {  # shape of ffprobe -show_streams -show_format for Keyed-Video (ProRes 422 LT 1080p60)
    "streams": [
        {"codec_type": "video", "codec_name": "prores", "width": 1920, "height": 1080, "r_frame_rate": "60/1"},
        {"codec_type": "audio", "codec_name": "pcm_s24le", "channels": 2},
        {"codec_type": "data"},
    ],
    "format": {"duration": "1731.4"},
}


def test_parse_probe():
    info = parse_probe(PROBE_KEYED)
    assert (info.fps, info.width, info.height, info.audio_channels) == ("60/1", 1920, 1080, 2)
    assert info.duration == pytest.approx(1731.4)
    wav_only = parse_probe({"streams": [{"codec_type": "audio", "channels": 1}], "format": {"duration": "60"}})
    assert wav_only.fps is None and wav_only.audio_channels == 1


def test_cover_art_is_not_video():
    info = parse_probe({"streams": [{"codec_type": "video", "disposition": {"attached_pic": 1}},
                                    {"codec_type": "audio", "channels": 2}], "format": {"duration": "3"}})
    assert info.fps is None


class _Runner:
    def __init__(self, code=0):
        self.code, self.calls = code, []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if self.code == 0 and "-i" in cmd:
            Path(cmd[-1]).write_bytes(b"RIFF")
        return subprocess.CompletedProcess(cmd, self.code, stdout="", stderr="boom")


def test_extract_builds_command_and_caches(tmp_path):
    runner = _Runner()
    audio = FfmpegAudio(tmp_path / "cache", ffmpeg="ffmpeg", runner=runner)
    src = Path("C:/Видео/Макашенец/Keyed-Video.mov")
    out = audio.extract(src, "abc")
    assert out == tmp_path / "cache" / "audio" / "abc.wav" and out.read_bytes() == b"RIFF"
    cmd = runner.calls[0]
    assert cmd[cmd.index("-i") + 1] == str(src)
    assert cmd[cmd.index("-ar") + 1] == "16000" and cmd[cmd.index("-ac") + 1] == "1"
    assert "-c:v" not in cmd and "-vn" in cmd  # audio only, the source is never re-encoded or written
    audio.extract(src, "abc")
    assert len(runner.calls) == 1


def test_extract_failure_is_reported(tmp_path):
    audio = FfmpegAudio(tmp_path, ffmpeg="ffmpeg", runner=_Runner(code=1))
    with pytest.raises(MediaError, match="boom"):
        audio.extract(Path("x.mov"), "fp")
    assert not (tmp_path / "audio" / "fp.wav").exists()


def test_find_tool_in_stacher(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    import os

    exe = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    (tmp_path / ".stacher" / "bin").mkdir(parents=True)
    (tmp_path / ".stacher" / "bin" / exe).write_bytes(b"")
    assert find_tool("ffprobe", home=tmp_path).endswith(exe)
    with pytest.raises(MediaError, match="not found"):
        find_tool("ffmpeg", home=tmp_path)


def test_fingerprint_changes_with_content_not_name(tmp_path):
    a, b = tmp_path / "a.mov", tmp_path / "b.mov"
    a.write_bytes(b"x" * 10_000_000)
    b.write_bytes(b"x" * 10_000_000)
    assert fast_fingerprint(a) == fast_fingerprint(b)
    b.write_bytes(b"x" * 5_000_000 + b"y" + b"x" * 4_999_999)
    assert fast_fingerprint(a) != fast_fingerprint(b)


def test_json_store(tmp_path):
    store = JsonFileStore(tmp_path)
    assert store.get("transcript/gigaam-v3/fp") is None
    store.put("transcript/gigaam-v3/fp", {"слово": 1})
    assert store.get("transcript/gigaam-v3/fp") == {"слово": 1}
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    assert store.get("broken") is None
    with pytest.raises(ValueError):
        store.put("../escape", {})
