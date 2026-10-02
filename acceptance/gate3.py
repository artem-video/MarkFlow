"""Gate 3 — the draft opened in real Premiere (CLAUDE.md). An empty or short timeline = FAIL.

Premiere is the judge: the draft is opened in Premiere and saved again under a new name
(File > Save As…  <name>_MF1_gate3.prproj). Premiere rewrites the whole file, so whatever it could not
read disappears from the re-saved project. This script compares that re-saved timeline with
edit_plan.json and checks the exported check frames.

    python -m acceptance.gate3 <draft.edit_plan.json> <resaved.prproj> --sequence MF_DRAFT --frames <folder>
    python -m acceptance.gate3 --episode acceptance/episodes/modnaya_propaganda.yaml   (finds everything itself)
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from acceptance.episode import report_dir
from markflow.domain.edit_plan import EditPlan, from_json
from markflow.infra.prproj.project import Project
from markflow.infra.prproj.reader import SequenceInfo, read_sequence
from markflow.infra.prproj.validator import structure_problems
from markflow.shared.timecode import format_clock, ticks_to_seconds

FRAME_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def compare(plan: EditPlan, info: SequenceInfo) -> list[str]:
    problems = []
    if not info.items:
        return ["timeline is EMPTY in Premiere"]
    want: Counter = Counter()
    for c in plan.clips:
        if c.video_track is not None:
            want[("video", c.video_track)] += 1
        for t in c.audio_tracks:
            want[("audio", t)] += 1
    have = Counter((i.kind, i.track) for i in info.items)
    for key in sorted(set(want) | set(have)):
        if want[key] != have[key]:
            problems.append(f"{key[0][0].upper()}{key[1] + 1}: {have[key]} clips in Premiere, plan has {want[key]}")
    plan_end = max(c.end for c in plan.clips)
    if info.duration < plan_end - info.frame_ticks:
        problems.append(f"timeline is SHORT: {format_clock(ticks_to_seconds(info.duration))} in Premiere, "
                        f"plan {format_clock(ticks_to_seconds(plan_end))}")
    covered = {(m.script_ref, m.start) for m in plan.markers if m.kind.value == "live_missing"}  # writer skips twins
    planned_markers = len(plan.markers)        + sum(1 for t in plan.text_layers if (t.script_ref, t.start) not in covered)
    if len(info.markers) < planned_markers:
        problems.append(f"{len(info.markers)} markers in Premiere, plan has {planned_markers}")
    return problems


def run(plan_path: Path, resaved: Path, sequence: str, frames: Path | None) -> int:
    plan = from_json(plan_path.read_text(encoding="utf-8"))
    project = Project.load(resaved)
    info = read_sequence(project, sequence)
    problems = compare(plan, info) + structure_problems(project)
    shots = sorted(p for p in frames.iterdir() if p.suffix.lower() in FRAME_EXT) if frames else []
    if len(shots) < 5:
        problems.append(f"{len(shots)} check frames exported, 5 needed")
    verdict = "OK" if not problems else "FAIL"
    lines = [f"# Gate 3 — {plan.episode}: {verdict}", "", f"- re-saved by Premiere: `{resaved}`",
             f"- sequence {sequence}: {len(info.items)} clips, {len(info.markers)} markers, "
             f"length {format_clock(ticks_to_seconds(info.duration))}",
             f"- per track: " + ", ".join(f"{k[0][0].upper()}{k[1] + 1}={n}"
                                          for k, n in sorted(Counter((i.kind, i.track) for i in info.items).items())),
             f"- check frames: {len(shots)} ({', '.join(p.name for p in shots[:5])})", ""]
    lines += ["## Problems", ""] + [f"- {p}" for p in problems] if problems else ["## Problems: none"]
    (report_dir() / f"gate3_{plan_path.stem.replace('.edit_plan', '')}.md").write_text("\n".join(lines) + "\n",
                                                                                        encoding="utf-8")
    print(verdict if not problems else "FAIL\n" + "\n".join(f"- {p}" for p in problems))
    return 0 if not problems else 1


def discover(episode: Path) -> tuple[Path, Path, str, Path]:
    """Latest draft plan, the project Premiere re-saved and the frames folder, from the episode file."""
    from acceptance.episode import Episode

    ep = Episode.load(episode)
    folder, stem = ep.out_folder, ep.base_project.stem
    plans = sorted(folder.glob(f"{stem}_MF1_draft*.edit_plan.json"), key=lambda p: p.stat().st_mtime)
    resaved = sorted(folder.glob(f"{stem}_MF1_gate3*.prproj"), key=lambda p: p.stat().st_mtime)
    if not plans:
        raise SystemExit(f"no {stem}_MF1_draft*.edit_plan.json in {folder}: run gate 2 first")
    if not resaved:
        raise SystemExit(f"no {stem}_MF1_gate3.prproj in {folder}: open the draft in Premiere and Save As that name")
    return plans[-1], resaved[-1], ep.sequence, report_dir() / f"frames_{episode.stem}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan", type=Path, nargs="?")
    ap.add_argument("resaved", type=Path, nargs="?")
    ap.add_argument("--sequence", default="MF_DRAFT")
    ap.add_argument("--frames", type=Path)
    ap.add_argument("--episode", type=Path, help="find plan, re-saved project and frames from the episode file")
    a = ap.parse_args()
    if a.episode:
        plan, resaved, sequence, frames = discover(a.episode)
        frames.mkdir(parents=True, exist_ok=True)
        sys.exit(run(plan, resaved, sequence, frames))
    if not (a.plan and a.resaved):
        ap.error("give PLAN and RESAVED, or --episode")
    sys.exit(run(a.plan, a.resaved, a.sequence, a.frames))


if __name__ == "__main__":
    main()
