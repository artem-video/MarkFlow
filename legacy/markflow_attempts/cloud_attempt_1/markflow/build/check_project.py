"""
check_project.py — валидатор .prproj без открытия Premiere.

Аналог check_xolod.py от Егора.
Принцип: «без ИТОГ: OK проект не отдаётся».

Проверяет:
  1. Файл парсится как XML
  2. Есть хотя бы одна Sequence
  3. Каждый ClipItem имеет Start < End
  4. Все MediaFilePath указывают на реально существующие файлы
     (если они доступны из облака — иначе пропускаем с WARNING)
  5. Маркеры имеют валидные In-тайм ≥ 0
  6. Нет дублирующихся ObjectID

Использование:
  python check_project.py project.prproj [template.prproj]
  Выход 0 = OK, выход 1 = ошибки.
"""

import sys
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CheckReport:
    errors:   list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, msg: str):   self.errors.append(f"[ERROR]   {msg}")
    def warn(self, msg: str):    self.warnings.append(f"[WARN]    {msg}")
    def ok(self) -> bool:        return len(self.errors) == 0


def check(prproj_path: str,
          template_path: Optional[str] = None) -> CheckReport:
    rep = CheckReport()
    path = Path(prproj_path)

    # 1. Файл существует
    if not path.exists():
        rep.error(f"Файл не найден: {prproj_path}")
        return rep

    # 2. Парсится как XML
    try:
        tree = ET.parse(prproj_path)
        root = tree.getroot()
    except ET.ParseError as e:
        rep.error(f"XML-ошибка: {e}")
        return rep

    # 3. Есть хотя бы одна Sequence
    sequences = root.findall(".//Sequence")
    if not sequences:
        rep.error("Нет ни одного элемента Sequence")
    else:
        print(f"  Sequences найдено: {len(sequences)}")

    # 4. Проверка ClipItem: Start < End
    clip_items = root.findall(".//ClipItem")
    print(f"  ClipItems найдено: {len(clip_items)}")
    for ci in clip_items:
        oid   = ci.get("ObjectID", "?")
        start = ci.findtext("Start")
        end   = ci.findtext("End")
        if start is None or end is None:
            rep.error(f"ClipItem {oid}: нет Start или End")
            continue
        try:
            s, e = int(start), int(end)
        except ValueError:
            rep.error(f"ClipItem {oid}: Start/End не числа")
            continue
        if s >= e:
            rep.error(f"ClipItem {oid}: Start ({s}) >= End ({e})")

    # 5. Пути к медиафайлам
    for fp_elem in root.findall(".//MediaFilePath"):
        p = fp_elem.text or ""
        # Конвертируем windows-путь в локальный если нужно
        local = Path(p.replace("\\", "/"))
        if not local.exists():
            rep.warn(f"Медиафайл не найден локально: {p}")

    # 6. Маркеры: время >= 0
    markers = root.findall(".//Marker")
    print(f"  Markers найдено: {len(markers)}")
    for m in markers:
        oid  = m.get("ObjectID", "?")
        in_t = m.findtext("In")
        if in_t is not None:
            try:
                if int(in_t) < 0:
                    rep.error(f"Marker {oid}: отрицательное время In={in_t}")
            except ValueError:
                rep.error(f"Marker {oid}: In не число")

    # 7. Уникальность ObjectID
    all_oids = [el.get("ObjectID") for el in root.iter() if el.get("ObjectID")]
    seen, dupes = set(), set()
    for oid in all_oids:
        if oid in seen:
            dupes.add(oid)
        seen.add(oid)
    if dupes:
        rep.error(f"Дублирующиеся ObjectID: {dupes}")

    # 8. Сравнение с шаблоном (если передан)
    if template_path:
        try:
            tmpl_tree = ET.parse(template_path)
            tmpl_root = tmpl_tree.getroot()
            tmpl_seqs = tmpl_root.findall(".//Sequence")
            if len(sequences) != len(tmpl_seqs):
                rep.warn(f"Количество Sequence отличается от шаблона: "
                         f"{len(sequences)} vs {len(tmpl_seqs)}")
        except Exception as e:
            rep.warn(f"Шаблон не прочитан: {e}")

    return rep


def main():
    if len(sys.argv) < 2:
        print("Usage: python check_project.py project.prproj [template.prproj]")
        sys.exit(1)

    prproj   = sys.argv[1]
    template = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"\n=== Проверка: {prproj} ===")
    rep = check(prproj, template)

    for w in rep.warnings:
        print(w)
    for e in rep.errors:
        print(e)

    if rep.ok():
        print("\nИТОГ: OK")
        sys.exit(0)
    else:
        print(f"\nИТОГ: ОШИБОК {len(rep.errors)}, ПРЕДУПРЕЖДЕНИЙ {len(rep.warnings)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
