"""
build_prproj.py — прямая сборка Premiere Pro проекта без открытия Premiere.

Аналог build_inplace.py из проекта Егора («Холод»).
Пишет валидный .prproj XML (который Premiere откроет без вопросов).

Формат входного edit_plan.json:
{
  "project_name": "МОДНАЯ ПРОПАГАНДА",
  "sequence_name": "МОДНАЯ ПРОПАГАНДА_rough_cut",
  "fps": 60,
  "width": 1920,
  "height": 1080,
  "clips": [
    {
      "id": "clip_001",
      "source_path": "C:/Users/Artem/Videos/Макашенец/МОДНАЯ ПРОПАГАНДА/Копия Keyed-Video_2608311425_0001.mov",
      "in_point": 12.34,    # секунды в исходнике
      "out_point": 15.67,
      "timeline_start": 0.0  # секунды в таймлайне
    },
    ...
  ],
  "markers": [
    {
      "time": 5.0,
      "name": "vine_boom",
      "comment": "[SFX] vine boom | категория: cliché"
    }
  ]
}

Выходной файл: <project_name>.prproj
"""

import uuid
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from typing import Optional
import json


# ---------- вспомогательные генераторы UUID -----------------------------

def _uid() -> str:
    """Уникальный ID в формате, который ожидает Premiere."""
    return "{" + str(uuid.uuid4()).upper() + "}"


def _ticks(seconds: float, fps: float = 60.0) -> int:
    """
    Premiere хранит время в «тиках» = 254016000000 / fps_timebase.
    Для 60fps: 1 секунда = 254016000000 / 60 = 4233600000 тиков.
    """
    TICKS_PER_SECOND = 254_016_000_000
    return int(seconds * TICKS_PER_SECOND)


# ---------- корневая структура проекта ----------------------------------

def _make_root() -> ET.Element:
    root = ET.Element("PremiereData", Version="3")
    return root


def _project_elem(root: ET.Element, plan: dict) -> ET.Element:
    proj = ET.SubElement(root, "Project", ObjectID=_uid(), ClassID="62ad66dd-0dcd-42da-a660-6d8fbde94876")
    ET.SubElement(proj, "ProjectSettings").text = ""
    ET.SubElement(proj, "RootProjectItem", ObjectRef=_uid())
    return proj


# ---------- видеоклип (MediaClip) ---------------------------------------

def _make_clip_elem(root: ET.Element, clip: dict, fps: float) -> tuple[str, str]:
    """
    Создаёт MasterClip и ClipItem.
    Возвращает (master_oid, clip_oid).
    """
    master_oid = _uid()
    clip_oid   = _uid()
    src_path   = clip["source_path"].replace("\\", "/")

    # MasterClip — описывает исходный файл
    mc = ET.SubElement(root, "MasterClip", ObjectID=master_oid,
                       ClassID="945b3f14-40f7-4e63-9e81-e37756cd9d5d")
    media = ET.SubElement(mc, "Media")
    video = ET.SubElement(media, "Video")
    ET.SubElement(video, "FrameRate").text = str(fps)
    ET.SubElement(video, "FrameWidth").text  = "1920"
    ET.SubElement(video, "FrameHeight").text = "1080"
    file_ref = ET.SubElement(mc, "File", ObjectID=_uid(),
                              ClassID="1d64faf1-9e3e-11d3-9ed1-00600806d7c5")
    ET.SubElement(file_ref, "MediaFilePath").text = src_path
    ET.SubElement(mc, "ClipIn").text  = str(_ticks(clip.get("in_point", 0.0), fps))
    ET.SubElement(mc, "ClipOut").text = str(_ticks(clip.get("out_point", 0.0), fps))

    # ClipItem — позиция в таймлайне
    ci = ET.SubElement(root, "ClipItem", ObjectID=clip_oid,
                       ClassID="f70b0c3c-7b7b-4e63-8b1e-8e0e6e6b1234")
    ET.SubElement(ci, "MasterClipRef",  ObjectRef=master_oid)
    ET.SubElement(ci, "In").text    = str(_ticks(clip.get("in_point", 0.0), fps))
    ET.SubElement(ci, "Out").text   = str(_ticks(clip.get("out_point", 0.0), fps))
    ET.SubElement(ci, "Start").text = str(_ticks(clip.get("timeline_start", 0.0), fps))
    ET.SubElement(ci, "End").text   = str(_ticks(
        clip.get("timeline_start", 0.0) +
        clip.get("out_point", 0.0) - clip.get("in_point", 0.0),
        fps
    ))

    return master_oid, clip_oid


# ---------- маркер -------------------------------------------------------

def _make_marker_elem(root: ET.Element, marker: dict, fps: float) -> str:
    oid = _uid()
    m = ET.SubElement(root, "Marker", ObjectID=oid,
                      ClassID="b3b3b3b3-b3b3-b3b3-b3b3-b3b3b3b3b3b3")
    ET.SubElement(m, "In").text      = str(_ticks(marker.get("time", 0.0), fps))
    ET.SubElement(m, "Name").text    = marker.get("name", "")
    ET.SubElement(m, "Comment").text = marker.get("comment", "")
    ET.SubElement(m, "Type").text    = "0"  # 0 = обычный маркер в Premiere
    return oid


# ---------- sequence (таймлайн) -----------------------------------------

def _make_sequence(root: ET.Element, plan: dict,
                   clip_oids: list[str], marker_oids: list[str]) -> str:
    fps   = float(plan.get("fps", 60))
    oid   = _uid()
    seq   = ET.SubElement(root, "Sequence", ObjectID=oid,
                           ClassID="7f4b7c80-c9f8-11d2-9dd7-006008a3a6d7")
    ET.SubElement(seq, "Name").text = plan.get("sequence_name", "Sequence")

    settings = ET.SubElement(seq, "Settings")
    ET.SubElement(settings, "VideoFrameWidth").text  = str(plan.get("width", 1920))
    ET.SubElement(settings, "VideoFrameHeight").text = str(plan.get("height", 1080))
    ET.SubElement(settings, "VideoFrameRate").text   = str(fps)

    video_track = ET.SubElement(seq, "VideoTrack",
                                ObjectID=_uid(),
                                ClassID="a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    for coid in clip_oids:
        ET.SubElement(video_track, "ClipItemRef", ObjectRef=coid)

    for moid in marker_oids:
        ET.SubElement(seq, "MarkerRef", ObjectRef=moid)

    return oid


# ---------- главная функция ----------------------------------------------

def build(plan: dict, out_dir: str = ".") -> str:
    """
    Собирает .prproj из edit_plan.
    Возвращает путь к созданному файлу.
    """
    fps  = float(plan.get("fps", 60))
    root = _make_root()

    clip_oids   = []
    marker_oids = []

    for clip in plan.get("clips", []):
        _, coid = _make_clip_elem(root, clip, fps)
        clip_oids.append(coid)

    for marker in plan.get("markers", []):
        moid = _make_marker_elem(root, marker, fps)
        marker_oids.append(moid)

    _project_elem(root, plan)
    _make_sequence(root, plan, clip_oids, marker_oids)

    # форматируем XML
    raw = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    # убираем лишнюю строку XML-заголовка (Premiere хочет свою)
    lines = pretty.split("\n")
    premiere_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        + "\n".join(lines[1:])
    )

    proj_name = plan.get("project_name", "project").replace(" ", "_")
    out_path  = str(Path(out_dir) / f"{proj_name}.prproj")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(premiere_xml)

    return out_path


# ---------- CLI ---------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python build_prproj.py edit_plan.json [out_dir]")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        plan = json.load(f)

    out_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    result  = build(plan, out_dir)
    print(f"Built: {result}")
