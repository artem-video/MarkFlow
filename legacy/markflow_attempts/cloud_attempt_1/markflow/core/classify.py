"""
classify.py — тегирование сегментов транскрипта по Style Profile.

Принимает список сегментов (из cut.py) + конфиг профиля.
Возвращает каждый сегмент с полем "tags": list[str] и "treatment": dict.

Логика: сначала простой keyword-матчинг (без LLM),
для edge-cases — передаём в Haiku отдельным пакетом.
"""

import re
import json
from typing import Optional

# импорт профиля
from markflow.profiles.makashenets_config import PROFILE


# ---------- keyword rules -----------------------------------------------

_RULES: list[tuple[str, str]] = [
    # (паттерн, категория)
    (r"\bпутин\b|\bпыпа\b|\bвладимир\s+владимирович\b|\bладимвладимыч\b", "putin_moment"),
    (r"\d[\d\s]*%|\d[\d\s]*(миллиард|миллион|тысяч|млрд|млн)", "impressive_number"),
    (r"\b(должен|обязан|обяза|следует|надо)\b.{0,30}\b(народ|россия|страна)\b", "cliché"),
    (r"\b(сказал|заявил|отметил|подчеркнул)\b", "important_quote"),
    (r"\b(х+[её]+рня|бля+|е+ба+ть|пизд|п+из|млять)\b", "profanity"),
    (r"\b(погиб|смерть|умер|убит|инвалид|вдов|пострадавш)\b", "scary_real"),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), cat) for p, cat in _RULES]


def _match_categories(text: str) -> list[str]:
    cats = []
    for rx, cat in _COMPILED:
        if rx.search(text) and cat not in cats:
            cats.append(cat)
    # Длинный синхрон > 25 слов → обивать мемами
    if len(text.split()) > 25 and "scary_real" not in cats:
        cats.append("long_sync")
    return cats or ["neutral"]


# ---------- публичный API -----------------------------------------------

def tag_segments(segments: list[dict]) -> list[dict]:
    """
    Добавляет к каждому сегменту:
      "categories": list[str]          — что это за момент
      "treatments": list[str]          — что делать (из профиля)
      "sfx":        list[str]          — звуки (из профиля)
      "red_zone":   bool               — трогать нельзя
    """
    classify_cfg = PROFILE["classify_categories"]
    result = []

    for seg in segments:
        text = seg.get("text", "")
        cats = _match_categories(text)

        treatments, sfx_list, red_zone = [], [], False
        for cat in cats:
            if cat == "scary_real":
                red_zone = True
                continue
            cfg = classify_cfg.get(cat, {})
            t = cfg.get("treatment")
            s = cfg.get("sfx")
            if t and t not in treatments:
                treatments.append(t)
            if s and s not in sfx_list:
                sfx_list.append(s)

        result.append({
            **seg,
            "categories":  cats,
            "treatments":  treatments,
            "sfx":         sfx_list,
            "red_zone":    red_zone,
        })

    return result


# ---------- CLI ---------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python classify.py segments.json [output.json]")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        segs = json.load(f)

    tagged = tag_segments(segs)

    out = sys.argv[2] if len(sys.argv) > 2 else None
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(tagged, f, ensure_ascii=False, indent=2)
        print(f"Tagged {len(tagged)} segments → {out}")
    else:
        print(json.dumps(tagged, ensure_ascii=False, indent=2))
