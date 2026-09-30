from markflow.domain.comments_rules import (
    Cue, cue_duration, instruction_text, is_nonstandard, place_cues, subtitle_text,
)
from markflow.shared.timecode import TICKS_PER_SECOND as S

FRAME = 8475667200  # 30000/1001


def test_links_and_timecodes_are_not_instruction_text():
    raw = "https://www.youtube.com/watch?v=xKo8uHegb5k&t=24sПоказать видео на ускоренке 1:31-1:38"
    assert instruction_text(raw) == "Показать видео на ускоренке"


def test_ordinary_instructions_stay_markers():
    for text in ("Файл 9012", "Показать Максимович", "Убираем строчку", "ВЫДЕЛИТЬ: участие в деятельности",
                 "https://youtu.be/d4li3Bk95Co 1:31-1:38 ВАЖНО! дать крупные планы с ней", "Кроп на слезах"):
        assert not is_nonstandard(text), text


def test_non_standard_instructions_become_subtitles():
    for text in ("Дать титр Инкумбент — действующий обладатель должности",
                 "Дать сноску (договориться с Андреем как они будут выглядеть)",
                 "Файл 8981 можно растянуть текст в ширину для комичности",
                 "тут можно увеличить на рот и на жирного эффект фишай",
                 "Можно сбоку от ведущего вывести со звуком мемным"):
        assert is_nonstandard(text), text


def test_a_link_alone_is_not_an_instruction():
    assert not is_nonstandard("https://t.me/bazabazon/22578")
    assert instruction_text("https://t.me/bazabazon/22578") == ""


def test_subtitle_text_is_one_short_line():
    long = "Дать титр " + "очень длинное определение " * 20
    out = subtitle_text(long + "\nhttps://x.ru/a")
    assert "\n" not in out and "http" not in out and len(out) <= 141 and out.endswith("…")


def test_duration_follows_the_phrase_but_stays_readable():
    assert cue_duration(0, FRAME) == round(4 * S / FRAME) * FRAME          # unknown span: 4 s
    assert cue_duration(S // 2, FRAME) == round(2 * S / FRAME) * FRAME     # too short: 2 s
    assert cue_duration(30 * S, FRAME) == round(6 * S / FRAME) * FRAME     # too long: 6 s
    assert cue_duration(1, FRAME) % FRAME == 0


def test_cues_do_not_overlap():
    cues = [Cue(10 * FRAME, 100 * FRAME, "a"), Cue(40 * FRAME, 50 * FRAME, "b"), Cue(40 * FRAME, 20 * FRAME, "c")]
    out = place_cues(cues, FRAME)
    assert [c.text for c in out] == ["a", "b", "c"]
    for a, b in zip(out, out[1:]):
        assert a.start + a.duration <= b.start
    assert out[0].duration == 30 * FRAME            # cut where b starts
    assert out[2].start == out[1].start + out[1].duration  # same start: follows
