from datetime import datetime

from markflow.domain.align import SourceText, align
from markflow.domain.edit_plan import SourceKind
from markflow.domain.triage_rules import (
    SourceMeta, classify_sources, recorded_at_from_name, recording_order, with_recording_time,
)
from tests.domain.test_align import U, _say, _t


def test_recording_time_from_camera_names():
    assert recorded_at_from_name("Копия 20260828_B0003.MP4") == (datetime(2026, 8, 28), 3)
    assert recorded_at_from_name("Копия Keyed-Video_2608311425_0001.mov") == (datetime(2026, 8, 31, 14, 25), 0)
    assert recorded_at_from_name("VO_MAKASHENETS_20260904.wav") == (datetime(2026, 9, 4), 0)
    assert recorded_at_from_name("live.mp4") is None


def _meta(name, fps="50", channels=2):
    return with_recording_time(SourceMeta(name, f"C:/ep/{name}", 600, fps, channels))


def test_order_and_kinds():
    metas = [_meta("20260915_B0001.MP4"), _meta("Копия 20260828_B0002.MP4"), _meta("Копия 20260828_B0001.MP4"),
             _meta("Keyed-Video_2608311425_0001.mov"), _meta("VO_MAKASHENETS_20260904.wav", fps=None, channels=1)]
    ordered = recording_order(metas)
    assert [m.id for m in ordered] == ["Копия 20260828_B0001.MP4", "Копия 20260828_B0002.MP4",
                                       "Keyed-Video_2608311425_0001.mov", "VO_MAKASHENETS_20260904.wav",
                                       "20260915_B0001.MP4"]
    l1 = "первая длинная строка сценария про пропаганду и блогеров"
    l2 = "вторая длинная строка которую потом переписали в доборе"
    l3 = "третья строка которую записали отдельно на хромакее потом"
    trans = {
        "Копия 20260828_B0001.MP4": _t("Копия 20260828_B0001.MP4", _say(l1, 1) + " " + _say(l2, 10)),
        "Копия 20260828_B0002.MP4": _t("Копия 20260828_B0002.MP4", _say("что-то своё вообще", 1)),
        "Keyed-Video_2608311425_0001.mov": _t("Keyed-Video_2608311425_0001.mov", _say(l3, 5)),
        "VO_MAKASHENETS_20260904.wav": _t("VO_MAKASHENETS_20260904.wav", _say("закадр текст", 1)),
        "20260915_B0001.MP4": _t("20260915_B0001.MP4", _say(l2, 3)),
    }
    texts = [SourceText.from_transcript(trans[m.id], i, m.audio_only) for i, m in enumerate(ordered)]
    a = align([U("B1.1", l1), U("B1.2", l2), U("B2.1", l3)], texts)
    smap = classify_sources(ordered, a)
    kinds = {r.meta.id: r.kind for r in smap.sources}
    assert kinds == {
        "Копия 20260828_B0001.MP4": SourceKind.MAIN, "Копия 20260828_B0002.MP4": SourceKind.MAIN,
        "Keyed-Video_2608311425_0001.mov": SourceKind.PICKUP, "VO_MAKASHENETS_20260904.wav": SourceKind.VOICEOVER,
        "20260915_B0001.MP4": SourceKind.RETAKE,
    }
    assert smap.unit_source["B1.2"] == "20260915_B0001.MP4"
    assert smap.overridden == (("B1.2", "Копия 20260828_B0001.MP4", "20260915_B0001.MP4"),)
