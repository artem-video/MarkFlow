import json
from pathlib import Path

import numpy as np
import pytest

from markflow.domain.align import SourceText, align
from markflow.domain.commands import OffScript, OffScriptRules, classify
from markflow.domain.cut import CutSettings, Piece, build_flow, finish, refine, shorten_pauses
from markflow.domain.loudness import Envelope
from markflow.domain.transcript import Transcript, Word
from markflow.infra.media.loudness import wav_envelope
from tests.domain.test_align import U, _say, _t

AUDIO = Path(__file__).resolve().parents[1] / "fixtures" / "audio"
RULES = OffScriptRules(crew_names=("Сань",))


@pytest.mark.parametrize("text,kind", [
    ("Пишем, да, Сань?", OffScript.COMMAND),
    ("На всякий случай записываю с запасом, но скорее всего можно брать фрагменты из прошлого стендапа.",
     OffScript.COMMAND),
    ("Ах, блядь, блядь", OffScript.IMPROV_FUNNY),
    ("ахаха ну ты даёшь", OffScript.IMPROV_FUNNY),
    ("Это какое-то недоразумение, мне кажется, нужно записать вторую часть реакта.", OffScript.IMPROV_MEANINGFUL),
    ("ну э", OffScript.JUNK),
])
def test_offscript_classes(text, kind):
    assert classify(text, RULES) == kind


def _flow(units, transcript):
    src = SourceText.from_transcript(transcript, 0)
    a = align(units, [src])
    return build_flow(a, {src.source_id: src}, RULES, script_texts=[u.text for u in units]), src


def test_flow_merges_reading_keeps_improv_marks_command_drops_retake():
    l1 = "финальное испытание в нашем видео алена максимович"
    l2 = "меган маркл есть у нас дома она же не популярная"
    l3 = "работает алена в жанре примитивного реакта обсуждает новости"
    text = " ".join([
        _say(l1, 1), _say(l2, 4.5),                         # continuous reading
        _say("это какое то недоразумение нужно записать вторую часть", 9),  # improvisation
        _say("давай еще раз сань", 13),                     # command
        _say("работает алена в жанре", 15),                 # torn take
        _say(l3, 18),
    ])
    cut, _ = _flow([U("B1.1", l1), U("B1.2", l2), U("B1.3", l3)], _t("kv", text))
    kinds = [p.kind for p in cut.pieces]
    assert kinds == ["script", "improv_meaningful", "script"]
    assert cut.pieces[0].unit_ids == ("B1.1", "B1.2")
    assert [m.kind for m in cut.markers] == ["command"]
    assert cut.bloopers == ()


def test_offscript_outside_the_flow_goes_to_bloopers():
    l1 = "первая длинная строка сценария про пропаганду в интернете"
    text = _say("кажется я заранее знаю ваш ответ друзья мои", 1) + " " + _say(l1, 10)
    cut, _ = _flow([U("B1.1", l1)], _t("kv", text))
    assert [p.kind for p in cut.bloopers] == ["improv_meaningful"]
    assert cut.bloopers[0].start == pytest.approx(1)


def test_missing_sentence_marker_and_no_merge_across_it():
    l1, l2, l3 = ("первая длинная строка сценария тут звучит", "вторая строка которой нет в записи совсем",
                  "третья длинная строка сценария тоже звучит")
    text = _say(l1, 1) + " " + _say(l3, 4)
    cut, _ = _flow([U("B1.1", l1), U("B1.2", l2), U("B1.3", l3)], _t("kv", text))
    assert len(cut.pieces) == 2 and [c.unit.id for c in cut.missing] == ["B1.2"]
    assert cut.markers[0].kind == "check"


def test_refine_uses_real_speech_onset_on_fixture_audio():
    """kv_0000s: ASR says 'И' starts at 14.97 s, but the sound starts at ~15.38 s."""
    env = wav_envelope(AUDIO / "kv_0000s_commands_and_intro_take1.wav")
    w = json.loads((AUDIO / "kv_0000s_commands_and_intro_take1.words.json").read_text(encoding="utf-8"))
    t = Transcript("kv", "w", 30.0, tuple(Word(x["w"], x["s"], x["e"]) for x in w))
    piece, warnings = refine(Piece("kv", 14.97, 29.19, "script"), SourceText.from_transcript(t, 0), env,
                             CutSettings())
    assert 15.25 <= piece.start <= 15.4 and warnings == []
    assert env.level(piece.start - 0.01, piece.start + 0.01) < -55
    assert piece.end >= 29.19


def _env_from(spans, total=20.0):
    db = np.full(int(total / 0.01), -80.0, np.float32)
    for a, b in spans:
        db[int(a / 0.01):int(b / 0.01)] = -25
    return Envelope(0.01, db)


def test_long_pause_is_shortened_to_profile_max():
    env = _env_from([(1, 3), (5, 7)])  # 2 s pause
    parts = shorten_pauses(Piece("kv", 0.96, 7.04, "script"), env, CutSettings(max_pause=0.5))
    assert len(parts) == 2
    assert parts[0].end == pytest.approx(3.25) and parts[1].start == pytest.approx(4.75)


def test_boundary_inside_continuous_sound_is_reported():
    env = _env_from([(0, 10)])
    t = _t("kv", "раз@1 два@5")
    piece, warnings = refine(Piece("kv", 5.0, 5.25, "script"), SourceText.from_transcript(t, 0), env,
                             CutSettings())
    assert len(warnings) == 2


def test_through_edit_keeps_exact_junction():
    env = _env_from([(1, 9)])
    t = _t("kv", _say("строка сценария длинная тут звучит хорошо", 1) + " " + _say("а вот и импровизация", 3.1))
    src = SourceText.from_transcript(t, 0)
    from markflow.domain.cut import RoughCut
    cut = RoughCut((Piece("kv", 1.0, 3.05, "script"), Piece("kv", 3.05, 4.3, "improv_meaningful")))
    done = finish(cut, {"kv": src}, {"kv": env})
    assert done.pieces[0].end == done.pieces[1].start == 3.05
