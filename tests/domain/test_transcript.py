import pytest

from markflow.domain.transcript import Transcript, Word, merge_fill_gaps


def T(engine, *words, duration=10.0):
    return Transcript("kv", engine, duration, tuple(Word(t, s, e) for t, s, e in words))


def test_order_and_bounds_are_checked():
    with pytest.raises(ValueError, match="out of order"):
        T("g", ("b", 2, 3), ("a", 1, 2))
    with pytest.raises(ValueError, match="ends before"):
        T("g", ("a", 2, 1))


def test_gaps_include_head_and_tail():
    t = T("g", ("раз", 1.0, 1.5), ("два", 1.6, 2.0), ("три", 5.0, 6.0))
    assert t.gaps(0.5) == [(0.0, 1.0), (2.0, 5.0), (6.0, 10.0)]


def test_merge_keeps_primary_and_fills_its_holes():
    giga = T("gigaam-v3", ("давай", 1.0, 1.4), ("ещё", 1.5, 1.8), ("раз", 6.0, 6.4))
    para = T("parakeet-v3", ("давай", 1.02, 1.4), ("ещё", 1.5, 1.8), ("тихо", 1.75, 1.9),
             ("сань", 3.0, 3.3), ("звук", 3.4, 3.8), ("раз", 6.0, 6.4))
    m = merge_fill_gaps(giga, para)
    assert [w.text for w in m.words] == ["давай", "ещё", "сань", "звук", "раз"]
    assert [w.engine for w in m.words] == ["gigaam-v3"] * 2 + ["parakeet-v3"] * 2 + ["gigaam-v3"]
    assert m.engine == "gigaam-v3+parakeet-v3"


def test_merge_refuses_different_sources():
    with pytest.raises(ValueError):
        merge_fill_gaps(T("g"), Transcript("other", "p", 10.0))


def test_dict_round_trip():
    t = T("gigaam-v3", ("Пишем,", 1.9, 2.68))
    assert Transcript.from_dict(t.to_dict()) == t
