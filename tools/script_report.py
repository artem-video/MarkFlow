"""Human-readable report of a parsed script (Russian), to check stage 1.2 by eye.

    python -m tools.script_report <text_and_threads.json> [<anchored_comments.json>] [--profile makashenets] > report.md
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from markflow.domain.script_model import CHECK_RU, BlockKind, Script, parse_script
from markflow.infra.google.docs_reader import load_connector_export
from markflow.profiles.loader import load_profile
from markflow.shared.timecode import format_clock

KIND_RU = {
    BlockKind.STANDUP: "стендап", BlockKind.LIVE: "лайв", BlockKind.QUOTE: "цитата",
    BlockKind.VOICEOVER: "закадр", BlockKind.INSERT: "вставка стендапа", BlockKind.BUTT: "встык",
    BlockKind.DIRECTION: "указание", BlockKind.PART: "часть",
}


def _short(text: str, n: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def render(script: Script) -> str:
    kinds = Counter(b.kind for b in script.blocks)
    words = sum(len(b.text.split()) for b in script.spoken_blocks)
    open_ = script.open_comments
    out = [
        f"# Разбор сценария «{script.title}»",
        "",
        "## Итог",
        "",
        "| Что | Сколько |",
        "|---|---|",
        *(f"| {KIND_RU[k]} | {kinds[k]} |" for k in BlockKind if kinds[k]),
        f"| слов ведущего (стендап + закадр) | {words} |",
        f"| комментариев открытых / привязано к тексту | {len(open_)} / {sum(c.anchored for c in open_)} |",
        f"| блоков в РЕЗЕРВЕ (в черновик не идут) | {len(script.reserve)} |",
        f"| расшифровок лайвов после сценария | {len(script.appendix)} |",
        "",
        "## ПРОВЕРИТЬ",
        "",
        "| Блок | Что не так | Текст |",
        "|---|---|---|",
    ]
    for b in script.blocks:
        for check in b.checks:
            shown = b.header or (b.lines[0] if b.lines else "")
            out.append(f"| {b.id} | {CHECK_RU.get(check, check)} | {_short(shown)} |")
    unanchored = [c for c in open_ if not c.anchored]
    if unanchored:
        out += ["", "Комментарии без места в тексте:", ""]
        out += [f"- {c.author}: {_short(c.text)}" for c in unanchored]
    out += ["", "## Лайвы", "", "| Блок | № | Подпись | Ссылка | Таймкоды |", "|---|---|---|---|---|"]
    for b in script.of_kind(BlockKind.LIVE):
        clocks = ", ".join(
            format_clock(c.start) + (f"–{format_clock(c.end)}" if c.end is not None else "") for c in b.clocks
        )
        link = b.links[0] if b.links else "—"
        out.append(f"| {b.id} | {b.number or ''} | {_short(b.label, 30)} | {link} | {clocks} |")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("text_and_threads", type=Path)
    ap.add_argument("anchored", type=Path, nargs="?")
    ap.add_argument("--profile", default="makashenets")
    args = ap.parse_args()
    raw = load_connector_export(args.text_and_threads, args.anchored)
    cues = load_profile(args.profile).script.vocabulary()
    print(render(parse_script(raw, cues)), end="")


if __name__ == "__main__":
    main()
