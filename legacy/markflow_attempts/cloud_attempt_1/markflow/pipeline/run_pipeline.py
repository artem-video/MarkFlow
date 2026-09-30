"""
run_pipeline.py — полный пайплайн от Google Doc до .prproj

Шаги:
  1. parse_doc   → script_sections.json  (разбор сценария)
  2. cut         → segments.json         (чистые сегменты из ASR)
  3. classify    → tagged.json           (тегирование по стилю)
  4. align       → aligned.json          (привязка сегментов к сценарию)
  5. build_prproj → project.prproj       (Premiere-файл без GUI)
  6. check_project → ИТОГ: OK / ОШИБОК N

Запуск:
  python -m markflow.pipeline.run_pipeline \\
    --gdoc_json    /path/to/gdoc_raw.json \\
    --words_json   /path/to/words.json \\
    --video_path   "C:/Users/Artem/Videos/МОДНАЯ ПРОПАГАНДА/video.mov" \\
    --out_dir      /path/to/output

Без --words_json запускается в режиме script-only:
  строит .prproj только по сценарию, без видеодорожек (маркеры + план).
"""

import argparse
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from markflow.core.parse_doc import load_and_parse_gdoc
from markflow.core.align import align, aligned_to_edit_plan
from markflow.build.build_prproj import build
from markflow.build.build_xml import build_xmeml
from markflow.build.check_project import check


def run(
    gdoc_json: str,
    words_json: str | None,
    video_path: str,
    out_dir: str,
    project_name: str = "Модная пропаганда",
    fps: float = 60.0,
):
    os.makedirs(out_dir, exist_ok=True)

    # ── 1. Parse script ──────────────────────────────────────────────────────
    print("[1/6] Parsing Google Doc script...")
    sections = load_and_parse_gdoc(gdoc_json, part=2)
    standups = [s for s in sections if s["type"] == "standup"]
    lives = [s for s in sections if s["type"] == "live"]
    print(f"     {len(standups)} СТЕНДАП, {len(lives)} ЛАЙВ")

    secs_path = os.path.join(out_dir, "script_sections.json")
    with open(secs_path, "w", encoding="utf-8") as f:
        json.dump(sections, f, ensure_ascii=False, indent=2)

    # ── 2+3. Cut + Classify (if words_json provided) ─────────────────────────
    segments = []
    if words_json and os.path.exists(words_json):
        print("[2/6] Running cut engine...")
        from markflow.core.cut import run as cut_run
        with open(words_json, encoding="utf-8") as f:
            words = json.load(f)
        segments = cut_run(words)
        seg_path = os.path.join(out_dir, "segments.json")
        with open(seg_path, "w", encoding="utf-8") as f:
            json.dump(segments, f, ensure_ascii=False, indent=2)
        print(f"     {len(segments)} clean segments")

        print("[3/6] Classifying segments...")
        from markflow.core.classify import tag_segments
        tagged = tag_segments(segments)
        tag_path = os.path.join(out_dir, "tagged.json")
        with open(tag_path, "w", encoding="utf-8") as f:
            json.dump(tagged, f, ensure_ascii=False, indent=2)
        cats = {}
        for t in tagged:
            c = t.get("category", "none")
            cats[c] = cats.get(c, 0) + 1
        print(f"     categories: {cats}")
    else:
        print("[2/6] No words.json — skipping ASR cut+classify (script-only mode)")
        print("[3/6] Skipped")

    # ── 4. Align ──────────────────────────────────────────────────────────────
    print("[4/6] Aligning script ↔ segments...")
    aligned = align(sections, segments, min_score=0.30)
    matched = sum(1 for e in aligned if e["type"] == "standup" and e.get("segment"))
    print(f"     matched {matched}/{len(standups)} standups")

    aligned_path = os.path.join(out_dir, "aligned.json")
    with open(aligned_path, "w", encoding="utf-8") as f:
        json.dump(aligned, f, ensure_ascii=False, indent=2)

    # ── 5. Build .prproj ──────────────────────────────────────────────────────
    print("[5/6] Building .prproj...")
    edit_plan = aligned_to_edit_plan(
        aligned,
        project_name=project_name,
        sequence_name="Мп_v1",
        fps=fps,
        video_path=video_path,
    )
    plan_path = os.path.join(out_dir, "edit_plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(edit_plan, f, ensure_ascii=False, indent=2)

    # Генерируем FCP7 XML — надёжный формат для импорта в Premiere Pro
    xml_path = build_xmeml(edit_plan, out_dir)
    print(f"     → {xml_path}  [FCP7 XML — импортируй через File → Import]")

    prproj_path = build(edit_plan, out_dir)
    print(f"     → {prproj_path}  [экспериментальный, может не открыться]")

    # ── 6. Validate ───────────────────────────────────────────────────────────
    print("[6/6] Validating .prproj...")
    report = check(prproj_path)
    if report.errors:
        print(f"ИТОГ: ОШИБОК {len(report.errors)}")
        for e in report.errors:
            print(f"  ERROR: {e}")
        sys.exit(1)
    else:
        print("ИТОГ: OK")
        print(f"\n✓ Готово:")
        print(f"  {xml_path}  ← ОТКРЫВАЙ ЭТОТ (File → Import в Premiere)")
        print(f"  {prproj_path}")
        print(f"  Clips on timeline: {len(edit_plan['clips'])}")
        print(f"  Markers:           {len(edit_plan['markers'])}")

    return prproj_path


def main():
    p = argparse.ArgumentParser(description="MarkFlow Pipeline")
    p.add_argument("--gdoc_json", required=True, help="Path to saved Google Doc JSON")
    p.add_argument("--words_json", default=None, help="Path to ASR words.json (optional)")
    p.add_argument("--video_path", default="", help="Path to source video file")
    p.add_argument("--out_dir", required=True, help="Output directory")
    p.add_argument("--project_name", default="Модная пропаганда")
    p.add_argument("--fps", type=float, default=60.0)
    args = p.parse_args()

    run(
        gdoc_json=args.gdoc_json,
        words_json=args.words_json,
        video_path=args.video_path,
        out_dir=args.out_dir,
        project_name=args.project_name,
        fps=args.fps,
    )


if __name__ == "__main__":
    main()
