"""
alternate_any.py  (Windows)
================
Универсальный скрипт чередования клипов между V1 и V2.

Перед работой проверяет окружение (версия Python, наличие библиотек;
недостающие библиотеки ставит через pip с вашего согласия) и только
потом спрашивает:
  1) путь к .prproj  (окно выбора файла; можно перетащить файл на alternate_any.bat)
  2) секвенцию       (показывает список, выбор номером)

Дальше берёт клипы ТОЛЬКО с первых двух видеодорожек (V1 и V2 —
названия не важны), сортирует по времени и раскладывает чередованием:
  чётные  [0, 2, 4, ...] → V1
  нечётные [1, 3, 5, ...] → V2

Остальные дорожки и аудио НЕ ТРОГАЮТСЯ. Позиции клипов на таймлайне
не меняются — меняется только их принадлежность дорожке.

Premiere Pro должен быть ЗАКРЫТ (скрипт правит файл проекта напрямую;
открытый проект Premiere держит в памяти и перезапишет изменения).
Перед записью создаётся резервная копия с меткой времени.

Запуск:
    python alternate_any.py [путь\\к\\проекту.prproj] [--dry-run]
    --dry-run  только показать план, файл не менять
"""

import gzip
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_VERSION = "1.1"

TICKS_PER_SECOND = 254016000000
SRC_TRACK = 0   # V1
DST_TRACK = 1   # V2

REQUIRED_PYTHON = (3, 10)

# Сторонние библиотеки: [("имя_для_import", "имя_для_pip"), ...]
# Сейчас список пуст — скрипту хватает стандартной поставки Python.
# Если появятся зависимости, впишите их сюда, установка предложится сама.
THIRD_PARTY_LIBS: list[tuple[str, str]] = []


# ── проверка окружения ────────────────────────────────────────────────────────

def preflight() -> None:
    """Проверяет окружение и ставит недостающие библиотеки (с согласия)."""
    print(f"=== alternate_any v{SCRIPT_VERSION} — проверка окружения ===")

    if sys.platform != "win32":
        print(f"  ВНИМАНИЕ: скрипт рассчитан на Windows, обнаружена система: {sys.platform}")

    if sys.version_info < REQUIRED_PYTHON:
        need = ".".join(map(str, REQUIRED_PYTHON))
        print(f"  ОШИБКА  нужен Python {need}+, установлен {sys.version.split()[0]}")
        print("          Скачайте свежий: https://www.python.org/downloads/")
        sys.exit(1)
    print(f"  OK      Python {sys.version.split()[0]}")

    try:
        import tkinter  # noqa: F401
        print("  OK      tkinter (окно выбора файла)")
    except ImportError:
        print("  WARN    tkinter недоступен — путь к проекту нужно будет ввести текстом.")
        print("          Лечится переустановкой Python с python.org (галочка 'tcl/tk and IDLE').")

    missing = []
    for import_name, pip_name in THIRD_PARTY_LIBS:
        try:
            __import__(import_name)
            print(f"  OK      {pip_name}")
        except ImportError:
            print(f"  НЕТ     {pip_name}")
            missing.append(pip_name)

    if missing:
        print(f"\nНе хватает библиотек: {', '.join(missing)}")
        if ask("Установить через pip? (y/n): ").strip().lower() != "y":
            print("Без этих библиотек скрипт работать не может. Отмена.")
            sys.exit(1)
        import subprocess
        r = subprocess.run([sys.executable, "-m", "pip", "install", *missing])
        if r.returncode != 0:
            print("ОШИБКА: pip не смог установить библиотеки. Смотрите вывод выше.")
            sys.exit(1)
        still_missing = []
        for import_name, pip_name in THIRD_PARTY_LIBS:
            if pip_name in missing:
                try:
                    __import__(import_name)
                except ImportError:
                    still_missing.append(pip_name)
        if still_missing:
            print(f"ОШИБКА: установлены, но не импортируются: {', '.join(still_missing)}")
            sys.exit(1)
        print("Библиотеки установлены.")
    elif not THIRD_PARTY_LIBS:
        print("  OK      сторонние библиотеки не требуются")

    print()


# ── разбор XML (логика идентична проверенному alternate_v1_to_v2.py) ─────────

def ticks_to_tc(ticks: int, fps: float = 25.0) -> str:
    secs = int(ticks) / TICKS_PER_SECOND
    h  = int(secs // 3600)
    m  = int((secs % 3600) // 60)
    s  = int(secs % 60)
    fr = int(round((secs % 1) * fps))
    return f"{h:02d}:{m:02d}:{s:02d}:{fr:02d}"


def extract_body_by_uid(xml: str, uid: str) -> tuple[str, int, int]:
    pos = xml.find(f'ObjectUID="{uid}"')
    if pos == -1:
        raise ValueError(f"UID {uid} не найден")
    ts = xml.rfind("<", 0, pos)
    tag = re.match(r"<(\w[\w.]*)", xml[ts:]).group(1)
    depth, i = 0, ts
    while i < len(xml):
        if xml[i:i+len(tag)+2] in (f"<{tag} ", f"<{tag}>"):
            depth += 1
        elif xml[i:i+len(tag)+3] == f"</{tag}>":
            depth -= 1
            if depth == 0:
                end = i + len(tag) + 3
                return xml[ts:end], ts, end
        i += 1
    raise ValueError(f"Не найден закрывающий тег для UID {uid}")


def find_sequences(xml: str) -> list[dict]:
    results = []
    for m in re.finditer(r'<Sequence ObjectUID="([^"]+)"', xml):
        uid = m.group(1)
        pos = m.start()
        depth, i = 0, pos
        body = None
        while i < len(xml):
            if xml[i:i+10] == "<Sequence " or xml[i:i+11] == "<Sequence>":
                depth += 1; i += 10
            elif xml[i:i+11] == "</Sequence>":
                depth -= 1
                if depth == 0:
                    body = xml[pos:i+11]; break
                i += 11
            else:
                i += 1
        if body is None:
            continue
        nm = re.search(r"<Name>([^<]+)</Name>", body)
        if nm:
            results.append({"name": nm.group(1), "uid": uid, "body": body})
    return results


def get_video_track_uids(xml: str, seq_uid: str) -> tuple[str, str, str, str]:
    """Возвращает (v1_uid, v2_uid, v1_name, v2_name) для первых двух видеодорожек."""
    seq_end = xml.find("</Sequence>", xml.find(f'ObjectUID="{seq_uid}"'))
    if seq_end == -1:
        raise ValueError(f"Не найдено тело секвенции {seq_uid}")
    section = xml[max(0, seq_end - 3000): seq_end]

    refs = re.findall(r'<Second ObjectRef="(\d+)"', section)
    if not refs:
        raise ValueError("TrackGroups не найдены в секвенции.")

    vtg_id = None
    for ref in refs:
        pos = xml.find(f'ObjectID="{ref}"')
        if pos == -1:
            continue
        ts = xml.rfind("<", 0, pos)
        tag = re.match(r"<(\w[\w.]*)", xml[ts:]).group(1)
        if tag == "VideoTrackGroup":
            vtg_id = ref
            break

    if not vtg_id:
        raise ValueError(f"VideoTrackGroup не найдена среди: {refs}")

    vtg_m = re.search(rf'ObjectID="{vtg_id}"[^>]*>([\s\S]+?)</VideoTrackGroup>', xml)
    if not vtg_m:
        raise ValueError(f"Тело VideoTrackGroup ID={vtg_id} не найдено.")
    vtg_body = vtg_m.group(1)

    tracks = re.findall(r'<Track Index="(\d+)" ObjectURef="([^"]+)"', vtg_body)
    tracks = sorted(tracks, key=lambda x: int(x[0]))

    if len(tracks) < 2:
        raise ValueError(f"В секвенции только {len(tracks)} видеодорожек, нужно минимум 2.")

    def track_name(uid: str) -> str:
        try:
            body, _, _ = extract_body_by_uid(xml, uid)
            nm = re.search(r"<MZ\.TrackName>([^<]+)</MZ\.TrackName>", body)
            return nm.group(1) if nm else uid[:8]
        except Exception:
            return uid[:8]

    v1_uid = tracks[SRC_TRACK][1]
    v2_uid = tracks[DST_TRACK][1]
    return v1_uid, v2_uid, track_name(v1_uid), track_name(v2_uid)


def get_track_clips(xml: str, track_body: str) -> list[dict]:
    items = re.findall(r'<TrackItem Index="\d+" ObjectRef="(\d+)"', track_body)
    clips = []
    for ref in items:
        pos = xml.find(f'ObjectID="{ref}"')
        if pos == -1:
            continue
        chunk = xml[xml.rfind("<", 0, pos): xml.rfind("<", 0, pos) + 600]
        sm = re.search(r"<Start>(\d+)</Start>", chunk)
        em = re.search(r"<End>(\d+)</End>", chunk)
        if sm:
            clips.append({"ref": ref, "start": int(sm.group(1)),
                          "end": int(em.group(1)) if em else 0})
    return sorted(clips, key=lambda x: x["start"])


def rebuild_track_items(refs: list[str]) -> str:
    lines = ['<TrackItems Version="1">']
    for i, ref in enumerate(refs):
        lines.append(f'\t\t\t\t\t<TrackItem Index="{i}" ObjectRef="{ref}"/>')
    lines.append("\t\t\t\t</TrackItems>")
    return "\n".join(lines)


def replace_track_items(track_body: str, new_xml: str) -> str:
    m = re.search(r'<TrackItems Version="\d+">', track_body)
    if m:
        end = track_body.find("</TrackItems>", m.start())
        if end != -1:
            return track_body[:m.start()] + new_xml + track_body[end + len("</TrackItems>"):]

    m2 = re.search(r'<TrackItems Version="\d+"\s*/>', track_body)
    if m2:
        return track_body[:m2.start()] + new_xml + track_body[m2.end():]

    ci = re.search(r'<ClipItems[^>]*>', track_body)
    if ci:
        insert_pos = ci.end()
        return track_body[:insert_pos] + "\n\t\t\t\t" + new_xml + track_body[insert_pos:]

    raise ValueError("Не найден <TrackItems> и <ClipItems> в теле дорожки")


# ── ввод пользователя ─────────────────────────────────────────────────────────

def ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        print("\n(нет интерактивного ввода — отмена)")
        sys.exit(1)


def pick_file(arg: str | None) -> Path:
    if arg:
        return Path(arg.strip('"'))
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="Выберите проект Premiere Pro",
            filetypes=[("Premiere Pro project", "*.prproj"), ("Все файлы", "*.*")],
        )
        root.destroy()
        if path:
            return Path(path)
    except Exception:
        pass
    raw = ask("Путь к .prproj: ").strip().strip('"')
    if not raw:
        print("Файл не выбран.")
        sys.exit(1)
    return Path(raw)


def pick_sequence(seqs: list[dict]) -> dict:
    print("\nСеквенции в проекте:")
    for i, s in enumerate(seqs, 1):
        print(f"  {i}. {s['name']}")
    while True:
        raw = ask(f"Номер секвенции (1-{len(seqs)}): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(seqs):
            return seqs[int(raw) - 1]
        print("Введите номер из списка.")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv

    preflight()

    prproj = pick_file(args[0] if args else None)
    if not prproj.exists():
        print(f"Файл не найден: {prproj}")
        sys.exit(1)
    if prproj.suffix.lower() != ".prproj":
        print(f"Это не .prproj: {prproj.name}")
        sys.exit(1)

    # Premiere держит открытый проект в памяти: правка файла в этот момент бессмысленна
    locks = list(prproj.parent.glob("*.prlock"))
    if locks:
        print(f"\nВНИМАНИЕ: найден lock-файл ({locks[0].name}) — похоже, проект открыт в Premiere Pro.")
        print("Закройте Premiere и запустите скрипт снова.")
        if ask("Всё равно продолжить? (y/n): ").strip().lower() != "y":
            sys.exit(1)

    print(f"\nПроект: {prproj}")

    with open(prproj, "rb") as f:
        raw = f.read()
    # Premiere пишет .prproj как gzip-XML; на всякий случай поддерживаем и чистый XML
    was_gzipped = raw[:2] == b"\x1f\x8b"
    xml = (gzip.decompress(raw) if was_gzipped else raw).decode("utf-8")

    seqs = find_sequences(xml)
    if not seqs:
        print("В проекте не найдено ни одной секвенции.")
        sys.exit(1)
    seq = pick_sequence(seqs)
    print(f"\nСеквенция: {seq['name']!r}")

    v1_uid, v2_uid, v1_name, v2_name = get_video_track_uids(xml, seq["uid"])
    print(f"V1: '{v1_name}'")
    print(f"V2: '{v2_name}'\n")

    v1_body, v1_s, v1_e = extract_body_by_uid(xml, v1_uid)
    v2_body, v2_s, v2_e = extract_body_by_uid(xml, v2_uid)

    v1_clips = get_track_clips(xml, v1_body)
    v2_clips = get_track_clips(xml, v2_body)

    print(f"Клипов на V1: {len(v1_clips)}")
    print(f"Клипов на V2: {len(v2_clips)}")

    all_clips = sorted(
        [(c["start"], c["ref"]) for c in v1_clips] +
        [(c["start"], c["ref"]) for c in v2_clips],
        key=lambda x: x[0]
    )
    total = len(all_clips)
    if total == 0:
        print("На V1 и V2 нет клипов — нечего раскладывать.")
        sys.exit(0)

    new_v1_refs = [r for i, (_, r) in enumerate(all_clips) if i % 2 == 0]
    new_v2_refs = [r for i, (_, r) in enumerate(all_clips) if i % 2 == 1]

    old_v1 = {c["ref"] for c in v1_clips}
    old_v2 = {c["ref"] for c in v2_clips}
    moves_to_v2 = sum(1 for r in new_v2_refs if r in old_v1)
    moves_to_v1 = sum(1 for r in new_v1_refs if r in old_v2)

    print(f"\nВсего клипов: {total}")
    print(f"Итог: V1 = {len(new_v1_refs)}, V2 = {len(new_v2_refs)}")
    print(f"Перемещений V1→V2: {moves_to_v2}")
    print(f"Перемещений V2→V1: {moves_to_v1}")

    print("\nПервые 20 клипов (финальный порядок):")
    ref_track = {c["ref"]: "V1" for c in v1_clips}
    ref_track.update({c["ref"]: "V2" for c in v2_clips})
    for i, (start, ref) in enumerate(all_clips[:20]):
        target = "V1" if i % 2 == 0 else "V2"
        orig   = ref_track.get(ref, "?")
        arrow  = f"  ← {orig}→{target}" if orig != target else ""
        print(f"  [{i:3d}] {ticks_to_tc(start)}  {target}{arrow}")

    if dry_run:
        print("\n[DRY RUN] Файл не изменён.")
        return

    print()
    if ask("Продолжить? (y/n): ").strip().lower() != "y":
        print("Отменено.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = prproj.with_name(prproj.name + f".backup_{stamp}")
    shutil.copy2(prproj, backup)
    print(f"Резервная копия: {backup.name}")

    new_v1_body = replace_track_items(v1_body, rebuild_track_items(new_v1_refs))
    new_v2_body = replace_track_items(v2_body, rebuild_track_items(new_v2_refs))

    if v1_s < v2_s:
        new_xml = xml[:v1_s] + new_v1_body + xml[v1_e:v2_s] + new_v2_body + xml[v2_e:]
    else:
        new_xml = xml[:v2_s] + new_v2_body + xml[v2_e:v1_s] + new_v1_body + xml[v1_e:]

    data = new_xml.encode("utf-8")
    if was_gzipped:
        data = gzip.compress(data, compresslevel=6)
    with open(prproj, "wb") as f:
        f.write(data)

    print(f"Сохранено: {prproj}")
    print("\nГотово! Откройте проект в Premiere Pro.")


if __name__ == "__main__":
    main()
