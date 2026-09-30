import pytest

from markflow.domain.script_model import (
    DEFAULT_CUES, BlockKind, RawComment, RawDoc, ScriptError, parse_script, select_part,
)

MINI = """# сценарий

**СТЕНДАП**
Что-то вышло из моды… <comment_start id=kix.a>Совсем вышло.<comment_end id=kix.a>
**001 ЛАЙВ (не могу найти)**
[**https://rutube.ru/video/6b2a/**](https://rutube.ru/video/6b2a/)
**1:15:13 я подготовлюсь — 1:15:16**
**Нужно с кропами нарезать динамично**
**СТЕНДАП**
Первая строка второго стендапа.
Вторая строка, где сказано про постиронию.
**ОТБИТЬ черным экраном**
Продолжение стендапа после указания.
**013 ЦИТАТА**
[**https://t.me/luka\\_ebkov/9135**](https://t.me/luka_ebkov/9135)
*Можно говорить что угодно.*
**ЗАКАДРОВЫЙ**
Текст за кадром.
**ЛАЙВ**
**https://www. **[**youtube.com/watch?v=AUU**](https://www.youtube.com/watch?v=AUU)
**13:12 супер — 13:22 был**
Короче говоря, это снова ведущий.
**ЧАСТЬ 2**
**СТЕНДАП**
Финальная фраза выпуска.
***КОНЕЦ***
**РЕЗЕРВ: **
**ЛАЙВ БУЗОВА**
[**https://www.youtube.com/watch?v=BFW**](https://www.youtube.com/watch?v=BFW)
# ЕБКОВ И АНТОНОВ
Ебков и Антонов <https://www.youtube.com/watch?v=tvH>
Speaker 1
00:08
Лукаепков
"""


def _doc(comments=()):
    return RawDoc(title="мини", markdown=MINI, comments=tuple(comments))


def test_blocks_kinds_and_order():
    s = parse_script(_doc())
    assert [b.kind for b in s.blocks] == [
        BlockKind.STANDUP, BlockKind.LIVE, BlockKind.STANDUP, BlockKind.DIRECTION, BlockKind.STANDUP,
        BlockKind.QUOTE, BlockKind.VOICEOVER, BlockKind.LIVE, BlockKind.STANDUP, BlockKind.PART, BlockKind.STANDUP,
    ]
    assert [b.id for b in s.blocks][:3] == ["B001", "B002", "B003"]


def test_standup_text_without_markdown_and_comment_marks():
    s = parse_script(_doc())
    assert s.blocks[0].lines == ("Что-то вышло из моды… Совсем вышло.",)
    assert s.blocks[2].lines == ("Первая строка второго стендапа.", "Вторая строка, где сказано про постиронию.")


def test_live_number_label_link_clock_and_note():
    live = parse_script(_doc()).blocks[1]
    assert (live.number, live.label) == ("001", "(не могу найти)")
    assert live.links == ("https://rutube.ru/video/6b2a/",)
    clock = live.clocks[0]
    assert (clock.start, clock.end, clock.start_words) == (4513.0, 4516.0, "я подготовлюсь")
    assert live.notes == ("Нужно с кропами нарезать динамично",)
    assert live.checks == ()


def test_broken_link_text_uses_target_and_range_words():
    live = parse_script(_doc()).blocks[7]
    assert live.links == ("https://www.youtube.com/watch?v=AUU",)
    assert (live.clocks[0].start_words, live.clocks[0].end_words) == ("супер", "был")


def test_text_after_direction_continues_standup_without_check():
    b = parse_script(_doc()).blocks[4]
    assert b.kind == BlockKind.STANDUP and b.implicit and b.checks == ()


def test_plain_text_after_live_is_standup_marked_for_check():
    b = parse_script(_doc()).blocks[8]
    assert b.kind == BlockKind.STANDUP
    assert b.lines == ("Короче говоря, это снова ведущий.",)
    assert b.checks == ("text right after a live without a СТЕНДАП header",)


def test_quote_and_voiceover():
    s = parse_script(_doc())
    assert s.blocks[5].links == ("https://t.me/luka_ebkov/9135",)
    assert s.blocks[5].lines == ("Можно говорить что угодно.",)
    assert s.blocks[6].lines == ("Текст за кадром.",) and s.blocks[6].spoken


def test_reserve_and_appendix_are_separate():
    s = parse_script(_doc())
    assert [b.label for b in s.reserve] == ["БУЗОВА"]
    assert s.reserve[0].in_reserve
    assert s.appendix[0].title == "ЕБКОВ И АНТОНОВ"
    assert s.appendix[0].links == ("https://www.youtube.com/watch?v=tvH",)
    assert all("Лукаепков" not in b.text for b in s.blocks)


def test_comment_anchored_by_text_and_by_mark():
    s = parse_script(_doc([
        RawComment(id="c1", author="Макашенец", text="Даем кадры", anchor_text="Вторая строка, где сказано"),
        RawComment(id="c2", author="Макашенец", text="мерч", anchor_id="kix.a"),
        RawComment(id="c3", author="Макашенец", text="ссылка: https://youtu.be/d4 1:31-1:38", anchor_text="нет такого"),
        RawComment(id="c4", author="Макашенец", text="сделано", resolved=True),
    ]))
    by_id = {c.id: c for c in s.comments}
    assert by_id["c1"].block_ids == ("B003",)
    assert by_id["c2"].block_ids == ("B001",)
    assert not by_id["c3"].anchored and by_id["c3"].links == ("https://youtu.be/d4",)
    assert by_id["c3"].clocks == ((91.0, 98.0),)
    assert [c.id for c in s.open_comments] == ["c1", "c2", "c3"]
    assert s.block("B003").comment_ids == ("c1",)
    assert s.block("B003").highlights[0].text == "Вторая строка, где сказано"
    assert len(s.warnings) == 1 and "c3" in s.warnings[0]


def test_comment_anchor_spanning_two_blocks():
    s = parse_script(_doc([RawComment(id="c", author="a", text="t", anchor_text="постиронию.\nОТБИТЬ черным")]))
    assert s.comments[0].block_ids == ("B003", "B004")


def test_fuzzy_anchor_after_small_edit_in_doc():
    s = parse_script(_doc([RawComment(id="c", author="a", text="t",
                                      anchor_text="Первая строчка второго стендапа")]))
    assert s.comments[0].block_ids == ("B003",)


def test_select_part_by_first_and_last_words():
    s = select_part(parse_script(_doc()), first_words="вторая строка где сказано", last_words="текст за кадром")
    assert s.blocks[0].lines == ("Вторая строка, где сказано про постиронию.",)
    assert s.blocks[-1].kind == BlockKind.VOICEOVER
    assert s.reserve == ()


def test_select_part_inside_one_block():
    s = select_part(parse_script(_doc()), first_words="вторая строка", last_words="вторая строка")
    assert [b.lines for b in s.blocks] == [("Вторая строка, где сказано про постиронию.",)]


def test_select_part_errors():
    s = parse_script(_doc())
    with pytest.raises(ScriptError, match="not found"):
        select_part(s, first_words="такой фразы нет нигде вообще")
    with pytest.raises(ScriptError, match="before"):
        select_part(s, first_words="финальная фраза", last_words="что-то вышло из моды")


def test_empty_doc_is_an_error():
    with pytest.raises(ScriptError):
        parse_script(RawDoc(title="x", markdown="# сценарий\n"))


def test_cue_vocabulary_longest_match():
    assert DEFAULT_CUES.match("ЗАКАДРОВЫЙ ТЕКСТ (скинул в ТГ)")[1] == "ЗАКАДРОВЫЙ ТЕКСТ"
    assert DEFAULT_CUES.match("ЛАЙВЫ") is None
    assert DEFAULT_CUES.match("Лайв") is None  # cues are UPPER CASE only
