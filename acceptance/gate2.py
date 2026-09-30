"""Gate 2 — the full chain on the real episode, on the PC, no Premiere (CLAUDE.md).

    python -m acceptance.gate2 acceptance/episodes/modnaya_propaganda.yaml

script -> transcripts (cache, stage 2.1) -> edit_plan.json -> <base>_MF1_draft.prproj (a new file) ->
validator (structure, plan, originals untouched) + PLAN §1 metrics. Prints OK or the list of problems and
writes acceptance/reports/<branch>/gate2_<episode>.md (+ source map, draft report, frames for gate 3).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from acceptance.episode import Episode, new_output_path, report_dir
from markflow.application.build_draft import DraftResult, SourceInput, build_draft
from markflow.application.reports import draft_md, source_map_md
from markflow.application.transcribe import TranscribeEpisode
from markflow.domain.edit_plan import Sequence, SourceKind, to_json
from markflow.domain.script_model import RawDoc, parse_script, select_part
from markflow.domain.triage_rules import SourceMeta, with_recording_time
from markflow.infra.cache import JsonFileStore, fast_fingerprint
from markflow.infra.google.docs_reader import GoogleDocsReader, load_connector_export
from markflow.infra.google.drive_service import CredentialsMissing, build_drive_service, credentials_path
from markflow.infra.media.ffmpeg import FfmpegAudio
from markflow.infra.prproj.project import Project
from markflow.infra.prproj.validator import plan_problems, structure_problems, untouched_problems
from markflow.infra.prproj.writer import write_plan
from markflow.profiles.loader import load_profile
from markflow.shared.timecode import format_clock, fps_from_frame_ticks, ticks_to_seconds


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def read_script(ep: Episode) -> tuple[RawDoc, str]:
    if ep.doc_id and credentials_path():
        try:
            return GoogleDocsReader(build_drive_service()).read(ep.doc_id), "Google Drive API"
        except CredentialsMissing as exc:
            log(f"Drive API unavailable ({exc}); using the saved export")
    if ep.export is None:
        raise SystemExit("no Google credentials and no saved export of the script")
    return load_connector_export(ep.export, ep.anchored), f"saved export {ep.export.name}"


def source_metas(paths: list[Path], audio: FfmpegAudio) -> list[SourceMeta]:
    metas = []
    for path in paths:
        info = audio.probe(path)
        metas.append(with_recording_time(SourceMeta(
            id=path.name, path=str(path), duration=info.duration, fps=info.fps, audio_channels=info.audio_channels,
            width=info.width, height=info.height)))
    return metas


def live_metas(lives_cache: Path | None, audio: FfmpegAudio) -> dict[str, SourceMeta]:
    """live_key(link) -> probed file, for every live the downloader stored (links that failed are simply absent)."""
    if lives_cache is None or not (lives_cache / "index.json").exists():
        return {}
    index = json.loads((lives_cache / "index.json").read_text(encoding="utf-8"))
    out = {}
    for key, rec in index.items():
        p = Path(rec["path"]) if rec.get("path") else None
        if p is None or not p.is_file():
            continue
        info = audio.probe(p)
        out[key] = SourceMeta(id=p.name, path=str(p), duration=info.duration, fps=info.fps,
                              audio_channels=info.audio_channels, width=info.width, height=info.height,
                              kind=SourceKind.LIVE)
    return out


def check_frames(result: DraftResult, n: int = 5) -> list[float]:
    """Timeline seconds for the gate-3 frames: middles of clips spread over the draft."""
    clips = sorted((c for c in result.plan.clips if c.video_track is not None and c.reason.value == "script"),
                   key=lambda c: c.start)
    if not clips:
        return []
    picks = [clips[min(len(clips) - 1, int(len(clips) * (k + 0.5) / n))] for k in range(n)]
    return [round(ticks_to_seconds(c.start + c.duration // 2), 2) for c in picks]


def run(ep_path: Path) -> int:
    ep = Episode.load(ep_path)
    profile = load_profile(ep.profile)
    out_dir = report_dir()
    problems: list[str] = []

    raw, script_from = read_script(ep)
    script = parse_script(raw, profile.script.vocabulary())
    if ep.first_words or ep.last_words:
        script = select_part(script, ep.first_words, ep.last_words)
    log(f"script: {len(script.blocks)} blocks ({script_from})")

    audio = FfmpegAudio(ep.cache)
    present = [p for p in ep.sources if p.is_file()]
    problems += [f"source not found (skipped): {p}" for p in ep.sources if not p.is_file()]
    if not present:
        raise SystemExit("none of the sources exist — check the paths in the episode file")
    metas = source_metas(present, audio)
    engines = []
    if ep.asr_engines:
        from markflow.infra.asr.onnx_engine import OnnxAsrFactory  # needs .[asr] only when the cache is cold
        engines = [OnnxAsrFactory(name) for name in ep.asr_engines]
    data = TranscribeEpisode(audio, engines, JsonFileStore(ep.cache), fast_fingerprint, log).run(present)
    inputs = [SourceInput(m, d.merged, d.envelope) for m, d in zip(metas, data)]

    base = Project.load(ep.base_project)
    seq = base.sequence(ep.sequence)
    width, height = base.frame_size(seq)
    sequence = Sequence(name=ep.sequence, fps=fps_from_frame_ticks(base.frame_ticks(seq)), width=width,
                        height=height)
    lives = live_metas(ep.lives_cache, audio)
    if ep.lives_cache:
        log(f"lives: {len(lives)} downloaded files found in {ep.lives_cache}")
    result = build_draft(script, inputs, profile, sequence, ep.name, lives)
    log(f"plan: {len(result.plan.clips)} clips, {len(result.plan.markers)} markers, "
        f"{format_clock(result.metrics.duration_s)}")

    ep.out_folder.mkdir(parents=True, exist_ok=True)
    out = new_output_path(ep.base_project, folder=ep.out_folder)
    written = write_plan(ep.base_project, result.plan, out, ep.sequence)
    out.with_suffix(".edit_plan.json").write_text(to_json(result.plan), encoding="utf-8")
    log(f"written: {out}")

    reloaded = Project.load(out)
    problems += structure_problems(reloaded)
    problems += plan_problems(reloaded, result.plan, ep.sequence, base)
    problems += untouched_problems(base, reloaded, ep.sequence)
    problems += result.metrics.problems()
    del written

    slug = ep_path.stem
    (out_dir / f"source_map_{slug}.md").write_text(source_map_md(result), encoding="utf-8")
    (out_dir / f"draft_{slug}.md").write_text(draft_md(result), encoding="utf-8")
    frames = check_frames(result)
    (out_dir / f"gate3_frames_{slug}.txt").write_text(
        "\n".join(format_clock(f) + f"  ({f:.2f} s)" for f in frames) + "\n", encoding="utf-8")
    verdict = "OK" if not problems else "FAIL"
    report = [f"# Gate 2 — {ep.name}: {verdict}", "", f"- script: {script_from}",
              f"- sources: {len(metas)}", f"- output: `{out}`", f"- plan: `{out.with_suffix('.edit_plan.json')}`",
              f"- clips: {len(result.plan.clips)}, markers: {len(result.plan.markers)}, "
              f"text layers: {len(result.plan.text_layers)}, length {format_clock(result.metrics.duration_s)}",
              "", "## Problems" if problems else "## Problems: none", ""]
    report += [f"- {p}" for p in problems]
    report += ["", f"Details: source_map_{slug}.md, draft_{slug}.md; frames for gate 3: gate3_frames_{slug}.txt"]
    (out_dir / f"gate2_{slug}.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(verdict if not problems else "FAIL\n" + "\n".join(f"- {p}" for p in problems))
    return 0 if not problems else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("episode", type=Path)
    sys.exit(run(ap.parse_args().episode))


if __name__ == "__main__":
    main()
