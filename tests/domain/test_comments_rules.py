from markflow.domain.comments_rules import Cue, cue_duration, is_for_editor, place_cues, subtitle_text
from markflow.shared.timecode import TICKS_PER_SECOND as S

FRAME = 8475667200  # 30000/1001


def test_subtitle_is_the_comment_word_for_word():
    raw = "ВИДЕО: https://vkvideo.ru/video-211437014_456248467\n47:48 Можно ускорить"
    assert subtitle_text(raw) == raw
    assert subtitle_text("  Файл 9012 \r\n\r\n") == "Файл 9012"


def test_comments_to_a_colleague_are_ignored():
    assert not is_for_editor("@alekseii.korostelev@gmail.com Лех, тут лайв нужен")
    assert not is_for_editor("@alekseii.korostelev@gmail.com поставишь плиз нужный лайв")
    assert not is_for_editor("   ")


def test_editing_comments_are_kept():
    for text in ("Файл 9012", "https://t.me/bazabazon/22578", "Дать титр Инкумбент — должность", "Кроп на слезах",
                 "ссылка: https://youtu.be/d4li3Bk95Co 1:31-1:38 ВАЖНО! дать крупные планы с ней"):
        assert is_for_editor(text), text


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
