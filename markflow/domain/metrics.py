"""Draft quality metrics from docs/PLAN.md §1 (Gate 2). Pure."""

from __future__ import annotations

from dataclasses import dataclass

from markflow.domain.align import Alignment
from markflow.domain.cut import RoughCut
from markflow.domain.edit_plan import ClipReason, EditPlan
from markflow.domain.loudness import Envelope
from markflow.shared.timecode import ticks_to_seconds


@dataclass(frozen=True)
class DraftMetrics:
    units_total: int
    units_found: int
    units_with_retakes: int
    last_take_chosen: int
    junk_share: float           # junk seconds / (kept speech + junk)
    unsafe_cuts: int            # clip edges on audio louder than the silence threshold
    improv_in_flow: int
    bloopers: int
    lives_placeholders: int
    markers_check: int
    duration_s: float

    @property
    def found_share(self) -> float:
        return self.units_found / max(1, self.units_total)

    @property
    def last_take_share(self) -> float:
        return self.last_take_chosen / max(1, self.units_with_retakes)

    def problems(self) -> list[str]:
        """Thresholds of the MVP table. Empty = OK."""
        out = []
        if self.units_found < self.units_total:
            out.append(f"строки сценария найдены не все: {self.units_found}/{self.units_total} "
                       f"(пропуски помечены ПРОВЕРИТЬ)")
        if self.units_with_retakes and self.last_take_share < 0.95:
            out.append(f"последний дубль выбран в {self.last_take_share:.0%} случаев (< 95 %)")
        if self.junk_share > 0.05:
            out.append(f"лишнего {self.junk_share:.1%} длительности (> 5 %)")
        if self.unsafe_cuts:
            out.append(f"резов по живому звуку: {self.unsafe_cuts}")
        return out


def measure(plan: EditPlan, alignment: Alignment, cut: RoughCut, envelopes: dict[str, Envelope],
            silence_db: float) -> DraftMetrics:
    retakes = [c for c in alignment.choices if len([o for o in c.takes if o.complete]) > 1]
    last = 0
    for c in retakes:
        complete = [o for o in c.takes if o.complete]
        if c.chosen is complete[-1]:
            last += 1
    kept = sum(ticks_to_seconds(c.duration) for c in plan.clips)
    unsafe = 0
    ordered = sorted(plan.clips, key=lambda c: c.start)
    for k, clip in enumerate(ordered):
        env = envelopes.get(clip.source_id)
        if env is None:
            continue
        prev = ordered[k - 1] if k else None
        nxt = ordered[k + 1] if k + 1 < len(ordered) else None
        through_in = prev is not None and prev.source_id == clip.source_id and prev.source_out == clip.source_in \
            and prev.end == clip.start
        through_out = nxt is not None and nxt.source_id == clip.source_id and nxt.source_in == clip.source_out \
            and clip.end == nxt.start
        for t, through in ((clip.source_in, through_in), (clip.source_out, through_out)):
            sec = ticks_to_seconds(t)
            if not through and env.level(max(0.0, sec - 0.01), sec + 0.01) >= silence_db:
                unsafe += 1
    return DraftMetrics(
        units_total=len(alignment.choices),
        units_found=sum(c.chosen is not None for c in alignment.choices),
        units_with_retakes=len(retakes),
        last_take_chosen=last,
        junk_share=round(cut.junk_seconds / max(1e-9, kept + cut.junk_seconds), 4),
        unsafe_cuts=unsafe,
        improv_in_flow=sum(1 for p in cut.pieces if p.kind != "script"),
        bloopers=sum(1 for c in plan.clips if c.reason in (ClipReason.IMPROV_FUNNY, ClipReason.IMPROV_MEANINGFUL))
        - sum(1 for p in cut.pieces if p.kind != "script"),
        lives_placeholders=len(plan.text_layers),
        markers_check=sum(1 for m in plan.markers if m.kind.value == "check"),
        duration_s=round(ticks_to_seconds(plan.duration), 2),
    )
