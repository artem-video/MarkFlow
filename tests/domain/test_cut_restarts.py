"""Restarts inside a take, improvisation as markers (Artem's review of the first draft)."""

from markflow.domain.align import SourceText, Token
from markflow.domain.cut import CutMarker, Piece, RoughCut, _restart_spans, drop_restarts, improv_to_markers


def _src(words: list[str], gap: float = 0.0) -> SourceText:
    toks, t = [], 0.0
    for w in words:
        toks.append(Token(w, t, t + 0.3, w))
        t += 0.3 + gap
    return SourceText("s", 0, tuple(toks))


def test_restart_keeps_the_later_reading():
    words = "если вам меньше тридцати если вам меньше тридцати лет погуглите".split()
    spans = _restart_spans(words)
    assert spans == [(0, 4)]


def test_single_content_word_repeat_is_emphasis_not_a_stutter():
    assert _restart_spans("очень очень важно".split()) == []
    assert _restart_spans("я я пошёл".split()) == [(0, 1)]  # one-letter stutter


def test_drop_restarts_splits_the_piece_and_counts_dropped_time():
    words = "а если вдруг меня если вдруг меня сейчас смотрят".split()
    src = _src(words)
    piece = Piece("s", 0.0, src.tokens[-1].end, "script", ("B1.1",), "B1", "x", ())
    cut = drop_restarts(RoughCut((piece,)), {"s": src})
    assert [p.text for p in cut.pieces] == ["а", "если вдруг меня сейчас смотрят"]
    assert cut.pieces[0].unit_ids == ("B1.1",) and cut.pieces[1].unit_ids == ()
    assert cut.pieces[1].end == piece.end
    assert cut.junk_seconds > 0


def test_improvisation_becomes_a_marker_and_bloopers_are_not_exported():
    script = Piece("s", 0, 2, "script", ("B1.1",), "B1", "text", ())
    improv = Piece("s", 2, 4, "improv_funny", (), "B1", "смешное", ())
    blooper = Piece("s", 10, 12, "improv_meaningful", (), None, "что то ещё", ())
    cut = improv_to_markers(RoughCut((script, improv, script), bloopers=(blooper,),
                                     markers=(CutMarker(-2, "command", "со съёмки"),)))
    assert [p.kind for p in cut.pieces] == ["script", "script"]
    assert cut.bloopers == ()
    notes = [m for m in cut.markers if m.kind == "improv"]
    assert len(notes) == 1 and notes[0].after_piece == 0 and "смешная" in notes[0].text
    assert not [m for m in cut.markers if m.after_piece == -2]


def test_retry_after_a_short_filler_drops_the_earlier_copy():
    words = "ли это шутка то ли то ли это шутка то ли подмигивание".split()
    spans = _restart_spans(words)
    gone = {k for a, b in spans for k in range(a, b)}
    kept = " ".join(w for k, w in enumerate(words) if k not in gone)
    assert kept == "то ли это шутка то ли подмигивание"


def test_a_piece_does_not_end_with_the_words_the_next_one_begins_with():
    from markflow.domain.cut import trim_seams

    words = "был пост и следом куча и следом куча мемов про него".split()
    src = _src(words)
    a = Piece("s", 0.0, src.tokens[4].end, "script", ("B1.1",), "B1", "был пост и следом куча", ())
    b = Piece("s", src.tokens[5].start, src.tokens[-1].end, "script", ("B1.2",), "B1", "и следом куча мемов про него", ())
    out = trim_seams(RoughCut((a, b)), {"s": src})
    assert out.pieces[0].text == "был пост" and out.pieces[0].end == src.tokens[1].end
    assert out.pieces[1] == b and out.junk_seconds > 0


def test_distinct_neighbours_are_left_alone():
    from markflow.domain.cut import trim_seams

    src = _src("один два три четыре пять шесть".split())
    a = Piece("s", 0.0, src.tokens[2].end, "script", (), "B1", "один два три", ())
    b = Piece("s", src.tokens[3].start, src.tokens[-1].end, "script", (), "B1", "четыре пять шесть", ())
    assert trim_seams(RoughCut((a, b)), {"s": src}).pieces == (a, b)
