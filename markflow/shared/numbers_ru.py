"""Digits -> Russian words, for matching a script against speech ('2020-го года' = 'две тысячи двадцатого года').

Matching is fuzzy, so the case endings need not be exact: a number followed by '-го'/'-й'/'год…' is spelled as an
ordinal (genitive), any other as a cardinal. Pure; numbers up to 999 999 999 are spelled, longer ones are kept.
"""

from __future__ import annotations

import re

_ONES = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять", "десять", "одиннадцать",
         "двенадцать", "тринадцать", "четырнадцать", "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать",
         "девятнадцать"]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]
_ORD_ONES = ["", "первого", "второго", "третьего", "четвертого", "пятого", "шестого", "седьмого", "восьмого",
             "девятого", "десятого", "одиннадцатого", "двенадцатого", "тринадцатого", "четырнадцатого",
             "пятнадцатого", "шестнадцатого", "семнадцатого", "восемнадцатого", "девятнадцатого"]
_ORD_TENS = ["", "", "двадцатого", "тридцатого", "сорокового", "пятидесятого", "шестидесятого", "семидесятого",
             "восьмидесятого", "девяностого"]
_ORD_HUNDREDS = ["", "сотого", "двухсотого", "трехсотого", "четырехсотого", "пятисотого", "шестисотого",
                 "семисотого", "восьмисотого", "девятисотого"]
_SCALES = [(1_000_000, "миллион", "миллиона", "миллионов", "миллионного"),
           (1_000, "тысяча", "тысячи", "тысяч", "тысячного")]


def _below_thousand(n: int, feminine: bool) -> list[str]:
    out = [_HUNDREDS[n // 100]] if n >= 100 else []
    n %= 100
    if n >= 20:
        out.append(_TENS[n // 10])
        n %= 10
    if n:
        word = _ONES[n]
        if feminine and n in (1, 2):
            word = {1: "одна", 2: "две"}[n]
        out.append(word)
    return [w for w in out if w]


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 100 in range(11, 15):
        return many
    return one if n % 10 == 1 else few if n % 10 in (2, 3, 4) else many


def spell(n: int, ordinal: bool = False) -> str:
    if n == 0:
        return "нулевого" if ordinal else "ноль"
    words: list[str] = []
    rest = n
    for scale, one, few, many, ord_word in _SCALES:
        part, rest = divmod(rest, scale)
        if part:
            if ordinal and rest == 0:  # '2000' -> 'двухтысячного'
                return " ".join(words + (_below_thousand(part, True) if part > 1 else []) + [ord_word])
            words += _below_thousand(part, scale == 1_000) + [_plural(part, one, few, many)]
    if rest:
        if ordinal:
            head, tail = rest - rest % 100, rest % 100
            if tail == 0:
                words.append(_ORD_HUNDREDS[head // 100])
            else:
                words += _below_thousand(head, False) if head else []
                if tail < 20:
                    words.append(_ORD_ONES[tail])
                elif tail % 10 == 0:
                    words.append(_ORD_TENS[tail // 10])
                else:
                    words += [_TENS[tail // 10], _ORD_ONES[tail % 10]]
        else:
            words += _below_thousand(rest, False)
    return " ".join(words)


_NUMBER = re.compile(r"(?<![\w.,])(\d{1,3}(?: \d{3})+|\d+)(-?(?:го|й|я|е|х|м|му|ми|ом|ем|ых|ыми|ого|ому|ой|ю|ая|ое|ые)\b)?"
                     r"(\s+(?:г\b|гг\b|год\w*))?", re.IGNORECASE)


def spell_numbers(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        digits = m.group(1).replace(" ", "")
        if len(digits) > 9:
            return m.group(0)
        ordinal = bool(m.group(2)) or bool(m.group(3))
        return " " + spell(int(digits), ordinal) + " " + (m.group(3) or "")
    return _NUMBER.sub(repl, text)
