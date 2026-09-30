"""Stage 2.1 on the PC: transcribe every source of an episode into the cache (GigaAM v3 + Parakeet-v3).

    python -m tools.transcribe_episode "C:\\...\\МОДНАЯ ПРОПАГАНДА" --cache "C:\\...\\MarkFlow\\cache"
    python -m tools.transcribe_episode file1.mov file2.wav --engines gigaam-v3

Sources are only read. A second run skips everything already in the cache.
Writes <cache>/report_2_1.md: per source — duration, words per engine, merged words, speech share.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from markflow.application.transcribe import SourceAudioData, TranscribeEpisode
from markflow.infra.asr.onnx_engine import OnnxAsrFactory
from markflow.infra.cache import JsonFileStore, fast_fingerprint
from markflow.infra.media.ffmpeg import FfmpegAudio

MEDIA = {".mov", ".mp4", ".mxf", ".mkv", ".wav", ".mp3", ".m4a"}


def collect(paths: list[Path]) -> list[Path]:
    out = []
    for p in paths:
        if p.is_dir():
            out += sorted(f for f in p.iterdir() if f.suffix.lower() in MEDIA and f.is_file())
        elif p.is_file():
            out.append(p)
        else:
            raise SystemExit(f"not found: {p}")
    return out


def report(results: list[SourceAudioData], seconds: float) -> str:
    lines = ["# Stage 2.1 — transcripts in cache", "", f"Run time: {seconds / 60:.1f} min", "",
             "| source | duration | " + " | ".join(results[0].transcripts) + " | merged | speech > -45 dB |",
             "|---|---|" + "---|" * (len(results[0].transcripts) + 2)]
    for r in results:
        env = r.envelope
        speech = float((env.db > -45).mean() * 100) if len(env.db) else 0.0
        counts = " | ".join(str(len(t.words)) for t in r.transcripts.values())
        lines.append(f"| {r.source.name} | {env.duration / 60:.1f} min | {counts} | {len(r.merged.words)} | "
                     f"{speech:.0f} % |")
    return "\n".join(lines) + "\n"


def dump(results: list[SourceAudioData], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for r in results:
        for engine, t in list(r.transcripts.items()) + [("merged", r.merged)]:
            data = json.dumps(t.to_dict(), ensure_ascii=False, separators=(",", ":"))
            (folder / f"{r.source.stem}.{engine}.json").write_text(data, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="+", type=Path)
    ap.add_argument("--cache", type=Path, default=Path.home() / "Videos" / "MarkFlow" / "cache")
    ap.add_argument("--engines", default="gigaam-v3,parakeet-v3", help="first = primary")
    ap.add_argument("--allow-cpu", action="store_true")
    ap.add_argument("--dump", type=Path, help="also write <stem>.<engine>.json per source here (small fixtures)")
    args = ap.parse_args()
    sources = collect(args.sources)
    engines = [OnnxAsrFactory(n.strip(), allow_cpu=args.allow_cpu) for n in args.engines.split(",")]
    t0 = time.time()
    use_case = TranscribeEpisode(FfmpegAudio(args.cache), engines, JsonFileStore(args.cache), fast_fingerprint,
                                 log=lambda m: print(time.strftime("%H:%M:%S"), m, flush=True))
    results = use_case.run(sources)
    text = report(results, time.time() - t0)
    (args.cache / "report_2_1.md").write_text(text, encoding="utf-8")
    if args.dump:
        dump(results, args.dump)
    print(text)


if __name__ == "__main__":
    main()
