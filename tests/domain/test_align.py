import json
from pathlib import Path

import pytest

from markflow.domain.align import SourceText, Unit, align, script_units, split_sentences
from markflow.domain.script_model import BlockKind, RawDoc, parse_script
from markflow.domain.transcript import Transcript, Word

FIX = Path(__file__).resolve().parents[1] / "fixtures"


def _t(source, text_with_times):
    """'слово@1.0 слово@1.3 ...' -> Transcript (each word lasts 0.25 s)."""
    words = []
    for item in text_with_times.split():
        w, t = item.rsplit("@", 1)
        words.append(Word(w, float(t), float(t) + 0.25))
    return Transcript(source, "test", words[-1].end + 5 if words else 10, tuple(words))


def _say(text, start, step=0.3):
    return " ".join(f"{w}@{start + i * step:.2f}" for i, w in enumerate(text.split()))


def U(uid, text, kind=BlockKind.STANDUP):
    from markflow.shared.text_norm import normalize
    return Unit(uid, uid.split(".")[0], kind, text, tuple(normalize(text).split()))


def test_split_sentences_keeps_min_length():
    assert split_sentences("Мда. После 22 года эту фразу услышали все. Да.") == [
        "Мда. После 22 года эту фразу услышали все. Да."]
    assert split_sentences("Первая длинная фраза тут. Вторая длинная фраза здесь!") == [
        "Первая длинная фраза тут.", "Вторая длинная фраза здесь!"]


def test_last_complete_take_wins():
    line = "есть такой типаж девушек который я встречал довольно часто"
    t = _t("kv", _say(line, 1) + " " + _say(line, 10) + " " + _say("есть такой типаж девушек", 20))
    a = align([U("B1.1", line)], [SourceText.from_transcript(t, 0)])
    c = a.choices[0]
    assert len(c.takes) == 2  # the torn third one covers < 50 %
    assert c.chosen.start == pytest.approx(10)


def test_partial_last_take_is_flagged_and_complete_one_used():
    line = "поступила на журфак мгу купалась в ванной с розами и без роз"
    t = _t("kv", _say(line, 1) + " " + _say("поступила на журфак мгу купалась в ванной", 20))
    c = align([U("B1.1", line)], [SourceText.from_transcript(t, 0)]).choices[0]
    assert c.chosen.start == pytest.approx(1)
    assert c.checks == ("после выбранного дубля есть недоговорённый",)


def test_missing_line_is_marked():
    t = _t("kv", _say("совсем другой текст про погоду и котов", 1))
    c = align([U("B1.1", "эта строка никогда не звучала в записи")], [SourceText.from_transcript(t, 0)]).choices[0]
    assert c.chosen is None and "не найдена" in c.checks[0]


def test_later_source_beats_earlier_source():
    line = "короче уровень аналитики вы поняли дальше будет хуже"
    main = _t("b1", _say(line, 100))
    retake = _t("b5", _say(line, 3))
    a = align([U("B1.1", line)], [SourceText.from_transcript(main, 0), SourceText.from_transcript(retake, 1)])
    assert a.choices[0].chosen.source_id == "b5"


def test_voiceover_prefers_the_vo_recording():
    line = "текст за кадром который ведущий записал в студии отдельно"
    cam = _t("cam", _say(line, 50))
    vo = _t("vo", _say(line, 2))
    a = align([U("B1.1", line, BlockKind.VOICEOVER)],
              [SourceText.from_transcript(vo, 0, audio_only=True), SourceText.from_transcript(cam, 1)])
    assert a.choices[0].chosen.source_id == "vo"


def test_isolated_short_coincidence_is_dropped():
    units = [U("B1.1", "на самом деле нет"), U("B2.1", "длинная строка которой в записи нет совсем никак")]
    t = _t("kv", _say("и вот на самом деле нет смысла", 400))
    a = align(units, [SourceText.from_transcript(t, 0)])
    assert a.choices[0].chosen is None


def test_real_keyed_take_choices():
    """Whole 28:51 Keyed-Video take (faster-whisper words) against the real script."""
    from markflow.infra.google.docs_reader import load_connector_export

    script = parse_script(load_connector_export(FIX / "script" / "modnaya_propaganda_gdoc_text_and_threads.json",
                                                FIX / "script" / "modnaya_propaganda_comments_anchored.json"))
    d = json.loads((FIX / "transcripts" / "keyed_video_faster_whisper.json").read_text(encoding="utf-8"))
    t = Transcript("keyed", "whisper", d["duration"],
                   tuple(Word(w["word"].strip(), w["start"], w["end"]) for s in d["segments"] for w in s["words"]))
    a = align(script_units(script), [SourceText.from_transcript(t, 0)])
    chosen = {c.unit.id: c.chosen for c in a.choices if c.chosen}
    assert len(chosen) >= 90
    blocks = {uid.split(".")[0] for uid in chosen}
    assert not blocks & {"B155", "B206"}  # short common phrases from parts not recorded here
    for uid, start in {"B327.1": 1195.6, "B330.1": 1280.4, "B336.7": 1626.0, "B014.1": 30.4, "B299.3": 444.6}.items():
        assert chosen[uid].start == pytest.approx(start, abs=0.2), uid
    retaken = [c for c in a.choices if len([o for o in c.takes if o.complete]) > 1]
    assert all(c.chosen is [o for o in c.takes if o.complete][-1] for c in retaken)
