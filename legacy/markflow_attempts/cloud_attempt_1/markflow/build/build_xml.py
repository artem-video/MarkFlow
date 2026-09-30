"""
build_xml.py — генерирует FCP7 XML (xmeml) для импорта в Premiere Pro.

Формат xmeml — промышленный стандарт обмена таймлайнами.
Premiere Pro открывает его через File → Import → [выбрать .xml файл].
Создаётся готовый сиквенс со всеми клипами и маркерами.

Входной edit_plan (тот же формат, что build_prproj):
{
  "project_name": "...",
  "sequence_name": "...",
  "fps": 60.0,
  "width": 3840,
  "height": 2160,
  "clips": [{"source_path": "...", "in_point": 5.0, "out_point": 52.0, "timeline_start": 0.0}],
  "markers": [{"time": 47.0, "comment": "ЛАЙВ | ..."}]
}
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
import os


def _frames(seconds: float, fps: float) -> int:
    return int(round(seconds * fps))


def _sub(parent: ET.Element, tag: str, text: str = "") -> ET.Element:
    el = ET.SubElement(parent, tag)
    if text:
        el.text = text
    return el


def _rate_elem(parent: ET.Element, fps: float) -> None:
    r = _sub(parent, "rate")
    # Premiere uses integer timebase; 60fps = 60
    _sub(r, "timebase", str(int(fps)))
    _sub(r, "ntsc", "FALSE")


def build_xmeml(plan: dict, out_dir: str = ".") -> str:
    """
    Строит FCP7 XML (.xml) файл для импорта в Premiere Pro.
    Возвращает путь к созданному файлу.
    """
    fps    = float(plan.get("fps", 60.0))
    width  = int(plan.get("width", 1920))
    height = int(plan.get("height", 1080))
    clips  = plan.get("clips", [])
    markers = plan.get("markers", [])
    seq_name = plan.get("sequence_name", "Sequence 01")

    # Считаем общую длину сиквенса
    total_frames = 0
    for c in clips:
        end_frame = _frames(c.get("timeline_start", 0) + (c.get("out_point", 0) - c.get("in_point", 0)), fps)
        if end_frame > total_frames:
            total_frames = end_frame
    # Добавляем место для маркеров за пределами клипов
    for m in markers:
        mf = _frames(m.get("time", 0), fps)
        if mf > total_frames:
            total_frames = mf + _frames(5.0, fps)
    if total_frames == 0:
        total_frames = _frames(60.0, fps)

    # ── XML root ────────────────────────────────────────────────────────────
    root = ET.Element("xmeml", version="5")
    seq = _sub(root, "sequence", "")
    _sub(seq, "name", seq_name)
    _sub(seq, "duration", str(total_frames))
    _rate_elem(seq, fps)

    # Настройки
    settings = _sub(seq, "settings")
    _sub(settings, "format")  # Premiere заполнит сам при импорте
    vtracks = _sub(settings, "videoTracks")
    _sub(vtracks, "track")

    # ── Media ────────────────────────────────────────────────────────────────
    media = _sub(seq, "media")
    video = _sub(media, "video")

    # Характеристики видео
    fmt = _sub(video, "format")
    sample = _sub(fmt, "samplecharacteristics")
    _rate_elem(sample, fps)
    _sub(sample, "width", str(width))
    _sub(sample, "height", str(height))
    _sub(sample, "pixelaspectratio", "square")
    _sub(sample, "fielddominance", "none")

    # Трек с клипами
    track = _sub(video, "track")

    # Уже добавленные файлы (дедупликация)
    file_ids: dict[str, str] = {}

    for idx, clip in enumerate(clips):
        src = clip.get("source_path", "")
        in_frames  = _frames(clip.get("in_point", 0.0), fps)
        out_frames = _frames(clip.get("out_point", 0.0), fps)
        tl_start   = _frames(clip.get("timeline_start", 0.0), fps)
        duration   = out_frames - in_frames
        tl_end     = tl_start + duration

        ci = _sub(track, "clipitem")
        ci.set("id", f"clipitem-{idx + 1}")

        src_name = Path(src).name
        _sub(ci, "name", src_name)
        _sub(ci, "duration", str(duration))
        _rate_elem(ci, fps)
        _sub(ci, "start", str(tl_start))
        _sub(ci, "end", str(tl_end))
        _sub(ci, "in", str(in_frames))
        _sub(ci, "out", str(out_frames))

        # Ссылка на файл (первое упоминание = полное описание, далее только id)
        if src not in file_ids:
            file_id = f"file-{len(file_ids) + 1}"
            file_ids[src] = file_id
            fe = _sub(ci, "file")
            fe.set("id", file_id)
            _sub(fe, "name", src_name)
            # Конвертируем путь Windows → URL
            url_path = src.replace("\\", "/")
            if ":" in url_path:
                url_path = "/" + url_path  # Windows: C:/... → /C:/...
            _sub(fe, "pathurl", f"file://{url_path}")
            _rate_elem(fe, fps)
            _sub(fe, "timecode").text = ""
        else:
            fe = _sub(ci, "file")
            fe.set("id", file_ids[src])

        # Подпись из сценария (для удобства в Premiere)
        label = clip.get("label", "")
        if label:
            _sub(ci, "comments").text = ""
            _sub(ci, "labels").text = ""
            _sub(ci, "note", label[:80])

    # ── Маркеры ──────────────────────────────────────────────────────────────
    for m in markers:
        mk = _sub(seq, "marker")
        _sub(mk, "name", m.get("name", "ЛАЙВ"))
        _sub(mk, "in", str(_frames(m.get("time", 0.0), fps)))
        _sub(mk, "out", "-1")
        _sub(mk, "comment", m.get("comment", "")[:200])

    # ── Форматируем XML ───────────────────────────────────────────────────────
    raw = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    # Убираем дублирующийся XML-заголовок
    lines = pretty.split("\n")
    xml_out = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + "\n".join(lines[1:])

    # Сохраняем
    proj_name = plan.get("project_name", "project").replace(" ", "_")
    os.makedirs(out_dir, exist_ok=True)
    out_path = str(Path(out_dir) / f"{proj_name}.xml")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml_out)

    return out_path
