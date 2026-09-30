"""ffmpeg / ffprobe: audio extraction for ASR and media probing. Sources are only read."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

SAMPLE_RATE = 16_000
Runner = Callable[..., subprocess.CompletedProcess]


class MediaError(RuntimeError):
    pass


def find_tool(name: str, home: Path | None = None) -> str:
    """ffmpeg/ffprobe on PATH or under %USERPROFILE%\\.stacher (where Artem's copy lives)."""
    found = shutil.which(name)
    if found:
        return found
    base = Path(home or Path.home()) / ".stacher"
    exe = name + (".exe" if os.name == "nt" else "")
    for candidate in sorted(base.rglob(exe)) if base.is_dir() else []:
        if candidate.is_file():
            return str(candidate)
    raise MediaError(f"{name} not found: put it on PATH or into {base}")


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    fps: str | None          # exact 'r_frame_rate', e.g. '60/1', '30000/1001'
    width: int | None
    height: int | None
    audio_channels: int
    audio_streams: int


def parse_probe(data: dict) -> MediaInfo:
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    duration = float(data.get("format", {}).get("duration") or (video or {}).get("duration") or 0)
    return MediaInfo(
        duration=duration,
        fps=video.get("r_frame_rate") if video else None,
        width=video.get("width") if video else None,
        height=video.get("height") if video else None,
        audio_channels=int(audio[0].get("channels", 0)) if audio else 0,
        audio_streams=len(audio),
    )


class FfmpegAudio:
    """Implements application.ports.Audio."""

    def __init__(self, cache_dir: Path, ffmpeg: str | None = None, ffprobe: str | None = None,
                 runner: Runner = subprocess.run):
        self.cache_dir = Path(cache_dir)
        self._ffmpeg, self._ffprobe, self._run = ffmpeg, ffprobe, runner

    @property
    def ffmpeg(self) -> str:
        self._ffmpeg = self._ffmpeg or find_tool("ffmpeg")
        return self._ffmpeg

    @property
    def ffprobe(self) -> str:
        self._ffprobe = self._ffprobe or find_tool("ffprobe")
        return self._ffprobe

    def extract_command(self, source: Path, out: Path) -> list[str]:
        return [self.ffmpeg, "-v", "error", "-nostdin", "-y", "-i", str(source), "-map", "0:a:0", "-vn",
                "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(out)]

    def extract(self, source: Path, fingerprint: str) -> Path:
        out = self.cache_dir / "audio" / f"{fingerprint}.wav"
        if out.is_file():
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.stem + ".part.wav")
        res = self._run(self.extract_command(source, tmp), capture_output=True, text=True)
        if res.returncode != 0:
            raise MediaError(f"ffmpeg failed on {source}: {res.stderr.strip()[-500:]}")
        os.replace(tmp, out)
        return out

    def read(self, wav: Path) -> tuple[np.ndarray, int]:
        with wave.open(str(wav), "rb") as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1:
                raise MediaError(f"{wav}: expected 16-bit mono WAV")
            rate = w.getframerate()
            data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        return data.astype(np.float32) / 32768.0, rate

    def probe(self, source: Path) -> MediaInfo:
        cmd = [self.ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(source)]
        res = self._run(cmd, capture_output=True, text=True, encoding="utf-8")
        if res.returncode != 0:
            raise MediaError(f"ffprobe failed on {source}: {res.stderr.strip()[-500:]}")
        return parse_probe(json.loads(res.stdout))
