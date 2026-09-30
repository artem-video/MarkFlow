"""
Тесты для build_prproj.py + check_project.py.
"""

import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from build.build_prproj import build
from build.check_project import check


MINIMAL_PLAN = {
    "project_name": "test_project",
    "sequence_name": "TEST_SEQ",
    "fps": 60,
    "width": 1920,
    "height": 1080,
    "clips": [
        {
            "id": "clip_001",
            "source_path": "C:/fake/video.mov",
            "in_point": 10.0,
            "out_point": 15.5,
            "timeline_start": 0.0,
        },
        {
            "id": "clip_002",
            "source_path": "C:/fake/video.mov",
            "in_point": 20.0,
            "out_point": 24.0,
            "timeline_start": 5.5,
        },
    ],
    "markers": [
        {
            "time": 3.0,
            "name": "vine_boom",
            "comment": "[SFX] vine boom | cliché"
        }
    ]
}


def test_build_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = build(MINIMAL_PLAN, tmpdir)
        assert os.path.exists(path), f"Файл не создан: {path}"
        assert path.endswith(".prproj"), f"Неверное расширение: {path}"
        size = os.path.getsize(path)
        assert size > 200, f"Файл слишком маленький: {size} байт"
        print(f"  test_build_creates_file: {path} ({size} байт) — OK")
        return path


def test_check_ok():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = build(MINIMAL_PLAN, tmpdir)
        rep  = check(path)
        # Ошибки структуры недопустимы; предупреждения о путях — ок
        structural_errors = [e for e in rep.errors if "Медиафайл" not in e]
        assert not structural_errors, f"Структурные ошибки: {structural_errors}"
        print(f"  test_check_ok: структура валидна — OK")
        if rep.warnings:
            print(f"    (предупреждения о путях: {len(rep.warnings)} — ожидаемо)")


def test_check_catches_bad_timing():
    """Если в plan Start > End — check должен поймать."""
    bad_plan = {
        **MINIMAL_PLAN,
        "clips": [{
            "id": "bad",
            "source_path": "C:/fake.mov",
            "in_point": 20.0,
            "out_point": 10.0,  # out < in = невалидно
            "timeline_start": 0.0,
        }]
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        path = build(bad_plan, tmpdir)
        rep  = check(path)
        timing_errors = [e for e in rep.errors if "Start" in e and "End" in e]
        assert timing_errors, "Не поймал невалидный тайминг"
        print(f"  test_check_catches_bad_timing: поймал ошибку тайминга — OK")


if __name__ == "__main__":
    print("\n=== Тесты build + check ===")
    test_build_creates_file()
    test_check_ok()
    test_check_catches_bad_timing()
    print("\nВсе тесты пройдены.")
