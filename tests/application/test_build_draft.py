import numpy as np
import pytest

from markflow.application.build_draft import SourceInput, build_draft
from markflow.domain.edit_plan import ClipReason, MarkerKind, Sequence, SourceKind, from_json, to_json
from markflow.domain.loudness import Envelope
from markflow.domain.metrics import DraftMetrics
from markflow.domain.script_model import RawComment, RawDoc, parse_script
from markflow.domain.transcript import Transcript, Word
from markflow.domain.triage_rules import SourceMeta, with_recording_time
from markflow.profiles.loader import load_profile
from markflow.shared.timecode import seconds_to_ticks, ticks_to_seconds

L1 = "финальное испытание в нашем видео это алена максимович"
L2 = "меган маркл есть у нас дома она же не популярная звезда"
L3 = "работает алена в жанре примитивного реакта и обсуждает новости"
DOC = f"""# сценарий
**СТЕНДАП**
{L1.capitalize()}. {L2.capitalize()}.
**001 ЛАЙВ МАКСИМОВИЧ**
[**https://youtu.be/abc**](https://youtu.be/abc)
**1:31 я ничего — 1:38 не понимаю**
**СТЕНДАП**
{L3.capitalize()}.
**Тут дать крупный план**
**ЛАЙВ**
***КОНЕЦ***
"""


def _words(items):
    out = []
    for text, start in items:
        for i, w in enumerate(text.split()):
            out.append(Word(w, start + i * 0.3, start + i * 0.3 + 0.25))
    return out


def _env(words, total):
    db = np.full(int(total / 0.01), -80.0, np.float32)
    for w in words:
        db[int(w.start / 0.01):int(w.end / 0.01)] = -25
    return Envelope(0.01, db)


@pytest.fixture(scope="module")
def result():
    profile = load_profile("makashenets")
    script = parse_script(RawDoc("мини", DOC, (
        RawComment("c1", "Макашенец", "дать кадры с ней", anchor_text="Меган Маркл есть у нас дома"),)),
        profile.script.vocabulary())
    main_words = _words([(L1, 2), (L2, 6), ("кажется я заранее знаю ваш ответ друзья", 12), (L3, 20),
                         ("пишем да сань", 30)])
    retake_words = _words([(L3, 3)])
    main = Transcript("Копия 20260828_B0001.MP4", "gigaam-v3+parakeet-v3", 40.0, tuple(main_words))
    retake = Transcript("20260915_B0001.MP4", "gigaam-v3+parakeet-v3", 15.0, tuple(retake_words))
    inputs = [
        SourceInput(with_recording_time(SourceMeta(main.source_id, "C:/ep/Копия 20260828_B0001.MP4", 40.0, "50",
                                                   2)), main, _env(main_words, 40.0)),
        SourceInput(with_recording_time(SourceMeta(retake.source_id, "C:/ep/20260915_B0001.MP4", 15.0, "50", 2)),
                    retake, _env(retake_words, 15.0)),
    ]
    return build_draft(script, inputs, profile, Sequence(name="MF1", fps="60", width=1920, height=1080),
                       "МИНИ")


def test_plan_is_valid_and_serialisable(result):
    plan = result.plan
    assert from_json(to_json(plan)) == plan
    assert {s.kind for s in plan.sources} == {SourceKind.MAIN, SourceKind.RETAKE}


def test_order_follows_the_script_with_live_placeholders(result):
    plan = result.plan
    script_clips = [c for c in plan.clips if c.reason == ClipReason.SCRIPT]
    assert list(dict.fromkeys(c.script_ref for c in script_clips)) == ["B001.1,B001.2", "B003.1"]
    assert len(script_clips) == 3  # the 1.2 s pause inside the first standup was shortened (split)
    b3 = next(c for c in script_clips if c.script_ref == "B003.1")
    assert b3.source_id == "20260915_B0001.MP4"  # the retake wins
    live = plan.text_layers[0]
    assert "ЛАЙВ 001 МАКСИМОВИЧ" in live.text and "https://youtu.be/abc" in live.text
    assert ticks_to_seconds(live.duration) == pytest.approx(7.0)
    assert script_clips[1].end <= live.start < b3.start


def test_clips_are_on_profile_tracks_and_frame_aligned(result):
    frame = 4_233_600_000  # 60 fps
    for c in result.plan.clips:
        assert c.video_track == 0 and c.audio_tracks == (0, 1)
        assert c.start % frame == 0 and c.duration % frame == 0


def test_improvisation_is_not_placed_on_the_timeline(result):
    """Artem: everything that is not in the script stays out of the timeline (no bloopers tail, no inline improv);
    off-script speech is only named by a marker."""
    plan = result.plan
    assert not [c for c in plan.clips if c.reason in (ClipReason.IMPROV_MEANINGFUL, ClipReason.IMPROV_FUNNY)]
    assert all(c.reason in (ClipReason.SCRIPT, ClipReason.VOICEOVER) for c in plan.clips)


def test_markers(result):
    kinds = [m.kind for m in result.plan.markers]
    assert MarkerKind.LIVE_MISSING in kinds and MarkerKind.SCRIPT_COMMENT not in kinds  # comments are subtitles
    comment = next(u for u in result.plan.subtitles if u.text.lower().startswith("дать кадры"))
    assert "Макашенец" not in comment.text + comment.note  # authors are not shown
    assert any(m.kind == MarkerKind.INFO and "крупный план" in m.name for m in result.plan.markers)
    assert any(m.kind == MarkerKind.CHECK and "лайв без ссылки" in m.name for m in result.plan.markers)


def test_metrics(result):
    m = result.metrics
    assert (m.units_total, m.units_found) == (3, 3)
    assert m.unsafe_cuts == 0 and m.junk_share <= 0.05
    assert m.problems() == []


def test_metric_thresholds():
    m = DraftMetrics(10, 4, 4, 3, 0.08, 2, 0, 0, 0, 0, 60.0)
    text = " ".join(m.problems())
    assert "4/10" in text and "75%" in text and "8.0%" in text and "живому" in text
    assert DraftMetrics(10, 9, 0, 0, 0.0, 0, 0, 0, 0, 0, 60.0).problems() == []  # missing lines are marked


def test_reports(result):
    from markflow.application.reports import draft_md, source_map_md

    smap = source_map_md(result)
    assert "| Копия 20260828_B0001.MP4 | основная съёмка | 28.08 00:00 |" in smap
    assert "| 20260915_B0001.MP4 | перезапись |" in smap
    assert "B003.1: Копия 20260828_B0001.MP4 → **20260915_B0001.MP4**" in smap
    draft = draft_md(result)
    assert "**Итог: OK**" in draft and "| строки сценария найдены | 3/3 (100%) |" in draft
