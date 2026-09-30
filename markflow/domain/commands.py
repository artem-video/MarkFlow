"""Off-script speech between takes: editor commands, improvisation (meaningful / funny), junk. Pure."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from markflow.shared.text_norm import normalize

# On-set talk to the operator/editor. Channel-specific names come from the profile (cut.crew_names).
COMMAND_PHRASES = (
    "пишем", "пишу", "мотор", "стоп", "камера", "звук", "дубль", "заново", "еще раз", "с начала", "сначала",
    "перепишу", "перезапишу", "записываю", "запишу", "запас", "оставим так", "давай оставим", "давай еще",
    "давай заново", "поехали", "подожди", "секунду", "не то", "не так", "так стоп", "окей", "все окей",
    "можно брать", "брать фрагменты", "из прошлого", "ну короче да",
)
STRONG_COMMANDS = ("записываю с запасом", "можно брать", "брать фрагменты", "перезапишу", "давай оставим",
                   "оставим так", "еще дубль", "с начала", "мотор")
LAUGH = ("ха", "хах", "хаха", "ахах", "ахаха", "хахаха", "хех", "хехе", "хи", "хихи", "гыгы")
SWEAR_ROOTS = ("хуй", "хуе", "хуя", "пизд", "ебл", "ебан", "ебат", "ебу", "еба", "бля", "сука", "сук", "долбоеб", "мудак",
               "говн", "жоп")


class OffScript(str, Enum):
    COMMAND = "command"
    IMPROV_FUNNY = "improv_funny"
    IMPROV_MEANINGFUL = "improv_meaningful"
    JUNK = "junk"          # fillers, false starts, sighs: cut silently (counts to the ≤5 % junk metric)


@dataclass(frozen=True)
class OffScriptRules:
    crew_names: tuple[str, ...] = ()
    min_improv_words: int = 4
    max_command_words: int = 10


def _has_phrase(norm: str, phrases: tuple[str, ...]) -> bool:
    padded = f" {norm} "
    return any(f" {p} " in padded for p in phrases)


def is_swear(word: str) -> bool:
    w = normalize(word)
    return any(w.startswith(r) or r in w and len(r) >= 4 for r in SWEAR_ROOTS)


def classify(text: str, rules: OffScriptRules = OffScriptRules()) -> OffScript:
    norm = normalize(text)
    words = norm.split()
    if not words:
        return OffScript.JUNK
    names = tuple(normalize(n) for n in rules.crew_names)
    strong = _has_phrase(norm, STRONG_COMMANDS)
    if (len(words) <= rules.max_command_words and (_has_phrase(norm, COMMAND_PHRASES) or _has_phrase(norm, names))) \
            or (strong and len(words) <= 2 * rules.max_command_words):
        return OffScript.COMMAND
    laughing = any(w in LAUGH or w.startswith(("хаха", "ахах")) for w in words)
    if laughing or (any(is_swear(w) for w in words) and len(words) >= 2):
        return OffScript.IMPROV_FUNNY
    if len(words) >= rules.min_improv_words:
        return OffScript.IMPROV_MEANINGFUL
    return OffScript.JUNK
