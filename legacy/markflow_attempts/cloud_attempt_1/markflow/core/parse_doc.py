"""
parse_doc.py — разбирает Google Doc сценарий в структуру для пайплайна.

Формат входного Google Doc:
  ЧАСТЬ 2
  **СТЕНДАП**
  текст стендапа...
  **ЛАЙВ**
  [URL](URL)
  MM:SS описание — MM:SS описание
  **ВСТЫК**
  ...

Выходной JSON:
  [
    {"type": "standup", "index": 0, "text": "..."},
    {"type": "live", "index": 1, "url": "...", "timecodes": [["0:20","0:51"]], "label": "..."},
    ...
  ]
"""

import re
import json
from typing import Optional


_TC_RE = re.compile(r"(\d{1,2}:\d{2})[^—\-\n]*[—\-][^—\-\n]*(\d{1,2}:\d{2})")
_URL_RE = re.compile(r"https?://[^\s\)\]\\]+")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_COMMENT_TAG_RE = re.compile(r"<comment_(?:start|end) id=[^>]+>")


def _tc_to_seconds(tc: str) -> float:
    parts = tc.strip().split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return 0.0


def _clean_url(raw: str) -> str:
    # Strip markdown bold/escape artifacts
    url = raw.replace("\\", "").replace("**", "").rstrip(")").rstrip("\\")
    return url


def parse(file_content: str, part: int = 2) -> list[dict]:
    """Parse Google Doc fileContent into a flat list of script sections."""

    # Find part marker
    if part == 2:
        start_marker = "ЧАСТЬ 2"
    else:
        start_marker = f"ЧАСТЬ {part}"

    start = file_content.find(start_marker)
    if start == -1:
        start = 0
    text = file_content[start:]

    # Find where part 3 begins (if exists) so we don't overshoot
    next_part = text.find("ЧАСТЬ 3", 10)
    if next_part != -1:
        text = text[:next_part]

    # Strip inline comment tags but preserve comment text for director notes
    # Format: <comment_start id=X>director note<comment_end id=X>
    director_notes: list[str] = []
    inline_note_re = re.compile(
        r"<comment_start id=([^>]+)>(.*?)<comment_end id=\1>", re.DOTALL
    )
    for m in inline_note_re.finditer(text):
        note_text = _COMMENT_TAG_RE.sub("", m.group(2)).strip()
        if note_text:
            director_notes.append(note_text)

    text = _COMMENT_TAG_RE.sub("", text)

    # Split by section headers: **СТЕНДАП**, **ЛАЙВ**, **ЛАЙВ АНТОНОВ**, **ВСТЫК** etc.
    section_header_re = re.compile(
        r"\n\*\*(?P<type>СТЕНДАП|ЛАЙВ(?:[^*]*)?|ВСТЫК(?:[^*]*)?)\*\*\n"
    )

    sections = []
    idx = 0
    positions = list(section_header_re.finditer(text))

    for i, m in enumerate(positions):
        header_type = m.group("type").strip()
        content_start = m.end()
        content_end = positions[i + 1].start() if i + 1 < len(positions) else len(text)
        body = text[content_start:content_end].strip()

        if header_type == "СТЕНДАП":
            # Clean markdown bold markers
            clean_body = _BOLD_RE.sub(r"\1", body).strip()
            sections.append({
                "type": "standup",
                "index": idx,
                "text": clean_body,
            })
        elif header_type.startswith("ЛАЙВ"):
            urls_raw = _URL_RE.findall(body)
            urls = [_clean_url(u) for u in urls_raw]
            url = urls[0] if urls else None

            tcs_raw = _TC_RE.findall(body)
            timecodes = [
                {
                    "in_tc": tc[0],
                    "out_tc": tc[1],
                    "in_sec": _tc_to_seconds(tc[0]),
                    "out_sec": _tc_to_seconds(tc[1]),
                }
                for tc in tcs_raw
                if _tc_to_seconds(tc[1]) > _tc_to_seconds(tc[0])  # skip malformed
            ]

            # Extract label from timecode line (text between in and out)
            label_parts = []
            for line in body.split("\n"):
                tc_m = _TC_RE.search(line)
                if tc_m:
                    between = line[tc_m.start():tc_m.end()]
                    # Take text after second timecode as label
                    after = line[tc_m.end():].strip(" *")
                    if after:
                        label_parts.append(after[:80])

            sections.append({
                "type": "live",
                "index": idx,
                "url": url,
                "source_label": header_type,
                "timecodes": timecodes,
                "label": "; ".join(label_parts) if label_parts else "",
            })
        else:
            # ВСТЫК or other
            sections.append({
                "type": "vstyk",
                "index": idx,
                "text": body.strip(),
            })

        idx += 1

    return sections


def sections_to_markers(sections: list[dict]) -> list[dict]:
    """Convert script sections to edit_plan markers for build_prproj."""
    markers = []
    for s in sections:
        if s["type"] == "live":
            for tc in s.get("timecodes", []):
                markers.append({
                    "time": 0,  # placeholder — will be filled by align.py
                    "comment": (
                        f"ЛАЙВ | {s.get('url','?')} | "
                        f"{tc['in_tc']}—{tc['out_tc']} | {s.get('label','')}"
                    )[:200],
                    "script_index": s["index"],
                    "live_url": s.get("url"),
                    "in_sec": tc["in_sec"],
                    "out_sec": tc["out_sec"],
                })
        elif s["type"] == "standup":
            markers.append({
                "time": 0,
                "comment": f"СТЕНДАП | {s['text'][:80]}",
                "script_index": s["index"],
            })
    return markers


def load_and_parse_gdoc(file_content_json_path: str, part: int = 2) -> list[dict]:
    """Load the saved Google Drive read_file_content JSON and parse it."""
    with open(file_content_json_path) as f:
        data = json.load(f)
    content = data.get("fileContent", "")
    return parse(content, part=part)


if __name__ == "__main__":
    import sys, os

    json_path = sys.argv[1] if len(sys.argv) > 1 else None
    if not json_path:
        print("Usage: python -m markflow.core.parse_doc <gdoc_json_path> [out.json]")
        sys.exit(1)

    out_path = sys.argv[2] if len(sys.argv) > 2 else "script_sections.json"
    sections = load_and_parse_gdoc(json_path, part=2)

    standups = [s for s in sections if s["type"] == "standup"]
    lives = [s for s in sections if s["type"] == "live"]
    print(f"Parsed: {len(standups)} СТЕНДАП, {len(lives)} ЛАЙВ")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sections, f, ensure_ascii=False, indent=2)
    print(f"Saved → {out_path}")
