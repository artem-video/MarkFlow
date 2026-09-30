"""
align.py — привязывает ASR-сегменты к тексту сценария.

Задача: у нас есть cut.py-сегменты (слова с таймкодами из видео) и
script_sections (СТЕНДАП-блоки из Google Doc). Нужно сопоставить их
по тексту — найти, какой сегмент видео соответствует какому стендапу.

Алгоритм:
  1. Нормализуем текст (строчные, убираем пунктуацию)
  2. Для каждого стендапа ищем лучший совпадающий сегмент через sliding
     window по словам (SequenceMatcher)
  3. Возвращаем aligned_plan.json: каждая запись = {standup_index, segment, score}

Выходной JSON:
  [
    {
      "type": "standup",
      "script_index": 0,
      "script_text": "...",
      "segment": {"start": 12.3, "end": 45.1, "text": "...", "take": 1},
      "score": 0.91
    },
    {
      "type": "live",
      "script_index": 1,
      "url": "...",
      "timecodes": [...],
      ...
    }
  ]
"""

import re
import json
from difflib import SequenceMatcher
from typing import Optional


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _words(text: str) -> list[str]:
    return _normalize(text).split()


def _score(a: str, b: str) -> float:
    wa = _words(a)
    wb = _words(b)
    if not wa or not wb:
        return 0.0
    # Use first 60 words of script standup for matching (opening phrase is most reliable)
    wa = wa[:60]
    return SequenceMatcher(None, wa, wb[:60]).ratio()


def align(
    sections: list[dict],
    segments: list[dict],
    min_score: float = 0.35,
) -> list[dict]:
    """
    Match script sections (СТЕНДАП) to ASR segments.

    Args:
        sections: output of parse_doc.parse()
        segments: output of cut.run() — [{start, end, text, take}, ...]
        min_score: minimum similarity to accept a match

    Returns:
        Flat ordered list of aligned entries.
    """
    result = []

    # Build pool of ASR segments sorted by start time
    pool = sorted(segments, key=lambda s: s["start"])
    used_indices: set[int] = set()

    for section in sections:
        if section["type"] != "standup":
            result.append(section)
            continue

        script_text = section.get("text", "")
        best_score = 0.0
        best_idx: Optional[int] = None

        for i, seg in enumerate(pool):
            if i in used_indices:
                continue
            sc = _score(script_text, seg.get("text", ""))
            if sc > best_score:
                best_score = sc
                best_idx = i

        if best_idx is not None and best_score >= min_score:
            used_indices.add(best_idx)
            result.append({
                **section,
                "segment": pool[best_idx],
                "score": round(best_score, 3),
            })
        else:
            # No match — mark as unmatched
            result.append({
                **section,
                "segment": None,
                "score": 0.0,
                "warning": "no_asr_match",
            })

    return result


def aligned_to_edit_plan(
    aligned: list[dict],
    project_name: str = "Модная пропаганда",
    sequence_name: str = "Мп_v1",
    fps: float = 60.0,
    width: int = 1920,
    height: int = 1080,
    video_path: str = "",
) -> dict:
    """
    Convert aligned sections into edit_plan.json for build_prproj.py.

    Clips = СТЕНДАП segments from the actual video file.
    Markers = all transitions (ЛАЙВ cue points, ВСТЫК etc.) for manual insertion.
    """
    clips = []
    markers = []
    timeline_cursor = 0.0
    GAP = 0.0  # seconds between clips on timeline

    for entry in aligned:
        if entry["type"] == "standup" and entry.get("segment"):
            seg = entry["segment"]
            duration = seg["end"] - seg["start"]
            clips.append({
                "source_path": video_path,
                "in_point": seg["start"],
                "out_point": seg["end"],
                "timeline_start": timeline_cursor,
                "label": entry["text"][:60],
            })
            timeline_cursor += duration + GAP

        elif entry["type"] == "live":
            # Insert a marker at current timeline position for each ЛАЙВ block
            for tc in entry.get("timecodes", []):
                markers.append({
                    "time": timeline_cursor,
                    "comment": (
                        f"ЛАЙВ | {entry.get('url','?')} | "
                        f"{tc['in_tc']}—{tc['out_tc']}"
                    )[:200],
                })
            # Leave placeholder gap on timeline = estimated duration of ЛАЙВ clips
            total_live = sum(
                max(0, tc["out_sec"] - tc["in_sec"])
                for tc in entry.get("timecodes", [])
            )
            if total_live > 0:
                timeline_cursor += total_live + GAP
            else:
                # If timecodes are empty still leave a marker
                if not entry.get("timecodes"):
                    markers.append({
                        "time": timeline_cursor,
                        "comment": f"ЛАЙВ | {entry.get('url','?')}",
                    })

    return {
        "project_name": project_name,
        "sequence_name": sequence_name,
        "fps": fps,
        "width": width,
        "height": height,
        "clips": clips,
        "markers": markers,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m markflow.core.align <script_sections.json> <asr_segments.json> [aligned.json]")
        sys.exit(1)

    sections_path = sys.argv[1]
    segments_path = sys.argv[2]
    out_path = sys.argv[3] if len(sys.argv) > 3 else "aligned.json"

    with open(sections_path, encoding="utf-8") as f:
        sections = json.load(f)
    with open(segments_path, encoding="utf-8") as f:
        segments = json.load(f)

    aligned = align(sections, segments)

    matched = sum(1 for e in aligned if e["type"] == "standup" and e.get("segment"))
    total_standups = sum(1 for e in aligned if e["type"] == "standup")
    print(f"Matched: {matched}/{total_standups} стендапов")

    unmatched = [e for e in aligned if e["type"] == "standup" and not e.get("segment")]
    if unmatched:
        print(f"WARNING: {len(unmatched)} стендапов без совпадения в ASR")
        for e in unmatched[:5]:
            print(f"  index={e['index']}: {e.get('text','')[:80]}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(aligned, f, ensure_ascii=False, indent=2)
    print(f"Saved → {out_path}")
