"""Human reports in Russian (markdown strings; writing files is the caller's job)."""

from __future__ import annotations

from collections import Counter

from markflow.application.build_draft import DraftResult
from markflow.domain.edit_plan import ClipReason, SourceKind
from markflow.shared.timecode import format_clock, ticks_to_seconds

KIND_RU = {
    SourceKind.MAIN: "основная съёмка", SourceKind.RETAKE: "перезапись", SourceKind.PICKUP: "добор",
    SourceKind.VOICEOVER: "закадр", SourceKind.LIVE: "лайв", SourceKind.ASSET: "ассет",
}


def source_map_md(result: DraftResult) -> str:
    sm = result.source_map
    out = ["# Карта исходников", "", "| Исходник | Что это | Дата | Длина | Строк сценария слышно | Взято отсюда | "
           "Перебил более ранний |", "|---|---|---|---|---|---|---|"]
    for r in sm.sources:
        date = r.meta.recorded_at.strftime("%d.%m %H:%M") if r.meta.recorded_at else "?"
        out.append(f"| {r.meta.id} | {KIND_RU[r.kind]} | {date} | {format_clock(r.meta.duration)} | "
                   f"{r.units_heard} | {r.units_chosen} | {r.overrides} |")
    total = len(result.alignment.choices)
    out += ["", f"Строк сценария: {total}, найдено: {total - len(sm.missing_units)}, "
                f"не найдено: {len(sm.missing_units)} (на таймлайне — маркеры ПРОВЕРИТЬ)."]
    if sm.overridden:
        out += ["", "## Где более поздняя запись перебила раннюю", ""]
        out += [f"- {uid}: {early} → **{late}**" for uid, early, late in sm.overridden[:200]]
    commands = [m for m in result.cut.markers if m.kind == "command"]
    if commands:
        out += ["", "## Команды и записки со съёмки", ""] + [f"- {m.text}" for m in commands]
    return "\n".join(out) + "\n"


def draft_md(result: DraftResult) -> str:
    m, plan = result.metrics, result.plan
    reasons = Counter(c.reason for c in plan.clips)
    problems = m.problems()
    out = [
        f"# Черновик «{plan.episode}» — {plan.stage.value}", "",
        "**Итог: " + ("OK" if not problems else "есть замечания") + "**", "",
        "| Метрика | Значение | Порог |", "|---|---|---|",
        f"| строки сценария найдены | {m.units_found}/{m.units_total} ({m.found_share:.0%}) | 100 % или ПРОВЕРИТЬ |",
        f"| последний дубль там, где перезаписано | {m.last_take_chosen}/{m.units_with_retakes} "
        f"({m.last_take_share:.0%}) | ≥ 95 % |",
        f"| лишнее между дублями | {m.junk_share:.1%} | ≤ 5 % |",
        f"| резы по живому звуку | {m.unsafe_cuts} | 0 |",
        f"| импровизация в потоке / в блуперсах | {m.improv_in_flow} / {m.bloopers} | не удалена, цветом |",
        f"| лайвы (пока текстом) | {m.lives_placeholders} | скачиваются на этапе 4 |",
        f"| маркеров ПРОВЕРИТЬ | {m.markers_check} | — |",
        f"| длина таймлайна | {format_clock(m.duration_s)} | — |",
        "", f"Клипов: {len(plan.clips)} (по сценарию {reasons[ClipReason.SCRIPT] + reasons[ClipReason.VOICEOVER]}, "
            f"импровизация {reasons[ClipReason.IMPROV_FUNNY] + reasons[ClipReason.IMPROV_MEANINGFUL]}), "
            f"маркеров: {len(plan.markers)}.",
    ]
    if problems:
        out += ["", "## Замечания", ""] + [f"- {p}" for p in problems]
    if result.cut.unsafe_cuts:
        out += ["", "## Резы, которые не удалось увести в тишину", ""]
        out += [f"- {w}" for w in result.cut.unsafe_cuts[:100]]
    out += ["", "## Первые 30 клипов", "", "| Время | Исходник | Откуда | Что |", "|---|---|---|---|"]
    for c in sorted(plan.clips, key=lambda c: c.start)[:30]:
        out.append(f"| {format_clock(ticks_to_seconds(c.start))} | {c.source_id} | "
                   f"{format_clock(ticks_to_seconds(c.source_in))} | {c.note[:60]} |")
    return "\n".join(out) + "\n"
