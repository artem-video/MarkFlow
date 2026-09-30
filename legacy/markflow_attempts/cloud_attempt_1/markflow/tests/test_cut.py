"""
Тесты для cut.py — на реальных паттернах из транскрипта «Модная пропаганда».
Пример из хэндовера: «...выходит план далиса... выходит пландалисы...
                       выходит пландалисы всё-таки работает...»
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.cut import (
    words_to_chunks, filter_director_commands,
    detect_takes, keep_last_take, chunks_to_segments,
    run, _similarity, Word,
)


# ---------- вспомогатели ------------------------------------------------

def make_words(phrases: list[tuple[str, float, float]]) -> list[dict]:
    """Из [(слово, start, end)] → список dict для run()."""
    return [{"word": w, "start": s, "end": e} for w, s, e in phrases]


# ---------- тест 1: повторяющиеся дубли --------------------------------

def test_duplicate_takes():
    """
    Три повтора одной фразы — должен остаться только последний.
    """
    words = make_words([
        # Дубль 1
        ("выходит", 0.0, 0.4), ("план", 0.45, 0.7), ("далисы", 0.75, 1.1),
        # пауза > MAX_GAP
        ("выходит", 2.6, 3.0), ("пландалисы", 3.05, 3.5),
        # пауза
        ("выходит", 5.2, 5.6), ("пландалисы", 5.65, 6.1),
        ("всё-таки", 6.15, 6.5), ("работает", 6.55, 7.0),
    ])
    result = run(words)
    # Должен остаться 1 или 2 сегмента (последний дубль)
    assert len(result) <= 2, f"Ожидали ≤2 сегмента, получили {len(result)}"
    # Последний сегмент должен содержать «работает» — это финальная версия
    last_text = result[-1]["text"]
    assert "работает" in last_text or "пландалисы" in last_text, \
        f"Последний сегмент не тот: {last_text}"
    print(f"  test_duplicate_takes: {len(result)} сегментов — OK")


# ---------- тест 2: служебные команды диктора --------------------------

def test_director_commands():
    """
    Фраза со словом «стоп» должна быть удалена.
    """
    words = make_words([
        ("хороший", 0.0, 0.3), ("текст", 0.35, 0.6),
        # пауза
        ("стоп", 2.0, 2.3), ("начнём", 2.4, 2.7), ("сначала", 2.75, 3.1),
        # пауза
        ("и", 5.0, 5.2), ("снова", 5.3, 5.6), ("хороший", 5.7, 6.0),
        ("текст", 6.05, 6.4),
    ])
    result = run(words)
    texts = [s["text"] for s in result]
    assert not any("стоп" in t for t in texts), "Команда диктора не удалена"
    print(f"  test_director_commands: команды удалены — OK")


# ---------- тест 3: пауза внутри куска < 1.3 с — НЕ режем ------------

def test_inner_pause_preserved():
    """
    Пауза 0.8 с внутри фразы — кусок должен остаться цельным.
    """
    words = make_words([
        ("первая", 0.0, 0.5),
        ("часть", 0.55, 1.0),
        # пауза 0.8 с — меньше MAX_GAP=1.3
        ("вторая", 1.8, 2.3),
        ("часть", 2.35, 2.8),
    ])
    result = run(words)
    assert len(result) == 1, f"Ожидали 1 сегмент (пауза < MAX_GAP), получили {len(result)}"
    print(f"  test_inner_pause_preserved: маленькая пауза не порезала — OK")


# ---------- тест 4: padding ---------------------------------------------

def test_padding():
    """
    Сегмент должен начинаться на 0.11 с раньше слова и заканчиваться на 0.26 с позже.
    """
    words = make_words([("слово", 5.0, 5.5)])
    result = run(words)
    assert len(result) == 1
    s = result[0]
    assert abs(s["start"] - (5.0 - 0.11)) < 0.01, f"start={s['start']}"
    assert abs(s["end"]   - (5.5 + 0.26)) < 0.01, f"end={s['end']}"
    print(f"  test_padding: padding OK")


# ---------- тест 5: similarity ----------------------------------------

def test_similarity():
    assert _similarity("выходит пландалисы", "выходит пландалисы всё-таки") > 0.7
    assert _similarity("совсем другая фраза", "вообще иные слова") < 0.5
    print(f"  test_similarity: OK")


# ---------- run all tests -----------------------------------------------

if __name__ == "__main__":
    print("\n=== Тесты cut.py ===")
    test_similarity()
    test_padding()
    test_inner_pause_preserved()
    test_director_commands()
    test_duplicate_takes()
    print("\nВсе тесты пройдены.")
