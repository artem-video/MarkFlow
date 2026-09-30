"""
cut.py — Rough-Cut Engine
Детект повторяющихся дублей по тексту транскрипта + выдача чистых отрезков.

Логика: как у Егора (проект «Холод»):
- Последний дубль побеждает
- Мусор между дублями выкидывается
- Паузы до 1.3 с внутри куска сохраняются
- Отступ: 0.11 с до речи, 0.26 с после

Входной формат (JSON):
  list of {"word": str, "start": float, "end": float}

Выходной формат (JSON):
  list of {"start": float, "end": float, "text": str, "take": int}
"""

import json
import re
from difflib import SequenceMatcher
from dataclasses import dataclass, asdict
from typing import Optional


# ---------- настройки ---------------------------------------------------

PRE_PAD   = 0.11   # секунд до первого слова
POST_PAD  = 0.26   # секунд после последнего слова
MAX_GAP   = 1.3    # пауза внутри куска — сохранять (не резать)
DUPE_SIM  = 0.82   # минимальная похожесть текстов чтобы считать их дублями

# Служебные фразы диктора, которые режем вместе с прилегающей тишиной
SKIP_PATTERNS = [
    r"\bстоп\b", r"\bотставить\b", r"\bещё раз\b", r"\bещ[её] один раз\b",
    r"\bначнём сначала\b", r"\bначнем сначала\b", r"\bповтор\b",
    r"\bзаново\b", r"\bнет.{0,10}не так\b",
]
_SKIP_RE = re.compile("|".join(SKIP_PATTERNS), re.IGNORECASE)


# ---------- типы данных -------------------------------------------------

@dataclass
class Word:
    word:  str
    start: float
    end:   float


@dataclass
class Segment:
    start: float
    end:   float
    text:  str
    take:  int   # номер дубля (последний = финальный)


# ---------- шаг 1: слова → сырые куски (по паузам) ----------------------

def words_to_chunks(words: list[Word]) -> list[list[Word]]:
    """Разбить список слов на куски по паузам > MAX_GAP."""
    if not words:
        return []
    chunks, cur = [], [words[0]]
    for w in words[1:]:
        if w.start - cur[-1].end > MAX_GAP:
            chunks.append(cur)
            cur = [w]
        else:
            cur.append(w)
    chunks.append(cur)
    return chunks


# ---------- шаг 2: убрать служебные команды диктора --------------------

def _chunk_text(chunk: list[Word]) -> str:
    return " ".join(w.word for w in chunk)


def filter_director_commands(chunks: list[list[Word]]) -> list[list[Word]]:
    """Убрать куски, которые целиком являются командой диктора."""
    clean = []
    for chunk in chunks:
        text = _chunk_text(chunk)
        if not _SKIP_RE.search(text):
            clean.append(chunk)
    return clean


# ---------- шаг 3: детект дублей ----------------------------------------

def _similarity(a: str, b: str) -> float:
    """Нормализованная схожесть двух строк (0–1)."""
    a_norm = re.sub(r"[^\w\s]", "", a.lower())
    b_norm = re.sub(r"[^\w\s]", "", b.lower())
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def detect_takes(chunks: list[list[Word]]) -> list[tuple[list[Word], int]]:
    """
    Пометить каждый кусок номером дубля.
    Одинаковые куски (sim >= DUPE_SIM) получают один и тот же take-id,
    нарастающий при каждом повторении.
    Возвращает [(chunk, take_number), ...]
    """
    tagged: list[tuple[list[Word], int]] = []
    # для каждого чанка ищем предыдущий похожий
    for i, chunk in enumerate(chunks):
        text_i = _chunk_text(chunk)
        take = 1
        for j in range(i - 1, -1, -1):
            text_j = _chunk_text(chunks[j])
            sim = _similarity(text_i, text_j)
            if sim >= DUPE_SIM:
                # нашли предыдущий дубль — возьмём его take + 1
                take = tagged[j][1] + 1
                break
        tagged.append((chunk, take))
    return tagged


# ---------- шаг 4: оставить только последний дубль каждой группы --------

def keep_last_take(tagged: list[tuple[list[Word], int]]) -> list[list[Word]]:
    """
    Для каждой группы (похожих) кусков оставляем только тот,
    после которого идёт НЕпохожий кусок (т.е. последний в серии).
    """
    result = []
    n = len(tagged)
    for i, (chunk, take) in enumerate(tagged):
        # Проверяем, есть ли СЛЕДУЮЩИЙ кусок с более высоким take той же группы
        is_last = True
        if i + 1 < n:
            next_chunk, next_take = tagged[i + 1]
            sim = _similarity(_chunk_text(chunk), _chunk_text(next_chunk))
            if sim >= DUPE_SIM and next_take > take:
                is_last = False  # есть лучшая копия позже
        if is_last:
            result.append(chunk)
    return result


# ---------- шаг 5: конвертировать в Segment с паддингом -----------------

def chunks_to_segments(chunks: list[list[Word]]) -> list[Segment]:
    segs = []
    for i, chunk in enumerate(chunks):
        start = max(0.0, chunk[0].start - PRE_PAD)
        end   = chunk[-1].end + POST_PAD
        text  = _chunk_text(chunk)
        segs.append(Segment(start=start, end=end, text=text, take=i + 1))
    return segs


# ---------- публичный API -----------------------------------------------

def run(
    words_json: list[dict],
    script_text: Optional[str] = None,   # на будущее: forced-alignment
) -> list[dict]:
    """
    Принимает список слов с таймкодами (из ASR).
    Возвращает чистые отрезки без дублей.

    words_json: [{"word": "привет", "start": 0.12, "end": 0.45}, ...]
    """
    words = [Word(**w) for w in words_json]

    chunks   = words_to_chunks(words)
    chunks   = filter_director_commands(chunks)
    tagged   = detect_takes(chunks)
    selected = keep_last_take(tagged)
    segments = chunks_to_segments(selected)

    return [asdict(s) for s in segments]


# ---------- CLI ---------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python cut.py words.json [output.json]")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        words_data = json.load(f)

    result = run(words_data)

    out_path = sys.argv[2] if len(sys.argv) > 2 else None
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(result)} segments → {out_path}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
