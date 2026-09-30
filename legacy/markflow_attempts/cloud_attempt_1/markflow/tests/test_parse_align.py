"""Tests for parse_doc.py and align.py."""

import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from markflow.core.parse_doc import parse
from markflow.core.align import align, aligned_to_edit_plan

# Minimal script fixture — mirrors real "Модная пропаганда" structure
FIXTURE_DOC = """ЧАСТЬ 2
-----
**СТЕНДАП**
Зачем я это все так подробно разбираю? А чтобы в полной мере представить логику всех этих молодых Z-базовичков.
**ЛАЙВ**
[**https://www.youtube.com/watch?v=Tm0L6YP6w_Y**](https://www.youtube.com/watch?v=Tm0L6YP6w_Y)
**0:20 Вероятность мобилизации — 0:51 паникующих**
**СТЕНДАП**
Дальше вы думаете, что Антонов скажет, почему вероятность мобилизации в России от двух до пяти процентов.
**ЛАЙВ**
[**https://www.youtube.com/watch?v=Tm0L6YP6w_Y**](https://www.youtube.com/watch?v=Tm0L6YP6w_Y)
**1:25 к вам приходит — 1:54 не третий**
**СТЕНДАП**
Стоп, так как раз скоро годовщина — четыре года, как Пыня провел уже первую мобилизацию?
**ЛАЙВ**
[**http://kremlin.ru/events/president/news/69390**](http://kremlin.ru/events/president/news/69390)
**9:30 считаю — 9:50 мобилизации**
"""


def _parse_fixture():
    return parse(FIXTURE_DOC, part=2)


def test_parse_counts_sections():
    secs = _parse_fixture()
    standups = [s for s in secs if s["type"] == "standup"]
    lives = [s for s in secs if s["type"] == "live"]
    assert len(standups) == 3, f"Expected 3 standups, got {len(standups)}"
    assert len(lives) == 3, f"Expected 3 lives, got {len(lives)}"


def test_parse_extracts_url():
    secs = _parse_fixture()
    lives = [s for s in secs if s["type"] == "live"]
    yt_url = lives[0]["url"]
    assert "youtube.com" in yt_url, f"Expected YouTube URL, got {yt_url}"


def test_parse_extracts_timecodes():
    secs = _parse_fixture()
    lives = [s for s in secs if s["type"] == "live"]
    first_tcs = lives[0]["timecodes"]
    assert len(first_tcs) == 1, f"Expected 1 timecode, got {len(first_tcs)}"
    assert first_tcs[0]["in_tc"] == "0:20"
    assert first_tcs[0]["out_tc"] == "0:51"
    assert first_tcs[0]["in_sec"] == 20.0
    assert first_tcs[0]["out_sec"] == 51.0


def test_parse_standup_text():
    secs = _parse_fixture()
    standups = [s for s in secs if s["type"] == "standup"]
    assert "Z-базовичков" in standups[0]["text"]


def test_parse_kremlin_url():
    secs = _parse_fixture()
    lives = [s for s in secs if s["type"] == "live"]
    kremlin = lives[2]
    assert "kremlin.ru" in kremlin["url"]
    assert kremlin["timecodes"][0]["in_sec"] == 570.0  # 9:30


def test_align_matches_standup():
    secs = _parse_fixture()
    # Create a mock ASR segment that matches the first standup
    segments = [
        {
            "start": 5.0,
            "end": 18.0,
            "text": "зачем я это все так подробно разбираю чтобы в полной мере представить логику всех этих молодых з базовичков",
            "take": 1,
        },
        {
            "start": 25.0,
            "end": 40.0,
            "text": "дальше вы думаете что антонов скажет почему вероятность мобилизации в России от двух до пяти процентов",
            "take": 1,
        },
    ]
    aligned = align(secs, segments, min_score=0.3)

    matched_standups = [e for e in aligned if e["type"] == "standup" and e.get("segment")]
    assert len(matched_standups) >= 2, f"Expected >=2 matched standups, got {len(matched_standups)}"

    first = matched_standups[0]
    assert first["segment"]["start"] == 5.0
    assert first["score"] > 0.3


def test_align_unmatched_when_empty_segments():
    secs = _parse_fixture()
    aligned = align(secs, [], min_score=0.3)
    standups = [e for e in aligned if e["type"] == "standup"]
    for s in standups:
        assert s.get("segment") is None
        assert s.get("warning") == "no_asr_match"


def test_edit_plan_markers_from_script():
    secs = _parse_fixture()
    aligned = align(secs, [], min_score=0.3)
    plan = aligned_to_edit_plan(aligned, video_path="/some/video.mov")

    # In script-only mode: 0 clips, but markers for each ЛАЙВ
    assert plan["clips"] == []
    assert len(plan["markers"]) >= 3  # 3 ЛАЙВ blocks
    marker_comments = [m["comment"] for m in plan["markers"]]
    assert any("youtube" in c.lower() or "kremlin" in c.lower() for c in marker_comments)


def test_edit_plan_clips_from_aligned():
    secs = _parse_fixture()
    segments = [
        {"start": 5.0, "end": 18.0, "text": "зачем я это все так подробно разбираю логику Z-базовичков", "take": 1},
    ]
    aligned = align(secs, segments, min_score=0.3)
    plan = aligned_to_edit_plan(aligned, video_path="/video.mov")

    assert len(plan["clips"]) >= 1
    clip = plan["clips"][0]
    assert clip["in_point"] == 5.0
    assert clip["out_point"] == 18.0
    assert clip["source_path"] == "/video.mov"


if __name__ == "__main__":
    tests = [
        test_parse_counts_sections,
        test_parse_extracts_url,
        test_parse_extracts_timecodes,
        test_parse_standup_text,
        test_parse_kremlin_url,
        test_align_matches_standup,
        test_align_unmatched_when_empty_segments,
        test_edit_plan_markers_from_script,
        test_edit_plan_clips_from_aligned,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  OK  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
