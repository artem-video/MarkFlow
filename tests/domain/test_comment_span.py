from markflow.domain.cut import Piece
from markflow.domain.timeline import _anchor_span

SEC = 254_016_000_000


def _piece(text: str) -> Piece:
    return Piece("s", 0.0, 1.0, "script", (), "B1", text, ())


def test_marker_spans_the_commented_phrase_within_one_clip():
    pieces = [(0, _piece("один два три четыре пять шесть семь восемь девять десять"))]
    start, length = _anchor_span(pieces, {0: 100 * SEC}, {0: 10 * SEC}, "Четыре пять шесть")
    assert start == 100 * SEC + 3 * SEC          # 4th word of ten, one second per word
    assert length == 3 * SEC                     # three words long


def test_marker_follows_the_phrase_across_clips():
    pieces = [(0, _piece("раз два три")), (1, _piece("четыре пять шесть"))]
    start, length = _anchor_span(pieces, {0: 0, 1: 50 * SEC}, {0: 3 * SEC, 1: 3 * SEC}, "три четыре пять")
    assert start == 2 * SEC and start + length == 50 * SEC + 2 * SEC


def test_no_match_gives_none():
    assert _anchor_span([(0, _piece("раз два три"))], {0: 0}, {0: SEC}, "совсем другое дело") is None
