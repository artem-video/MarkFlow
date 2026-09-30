"""Gate 2 end to end in the cloud: real script + real Keyed-Video transcript + a Premiere-saved project.

Only what needs the PC is faked: ffprobe (media info), ASR (the transcript is put into the cache as if stage
2.1 had run) and the loudness envelope (built from word times).
"""

import gzip
import json
from pathlib import Path

import numpy as np
import pytest

import acceptance.gate2 as gate2
from markflow.application.transcribe import TranscribeEpisode
from markflow.domain.loudness import Envelope
from markflow.domain.transcript import Transcript, Word
from markflow.infra.cache import JsonFileStore, fast_fingerprint
from markflow.infra.media.ffmpeg import FfmpegAudio, MediaInfo
from markflow.infra.prproj.project import Project
from markflow.infra.prproj.reader import read_sequence
from tests.infra.prproj.test_prproj import SEQ, SMALL, empty_sequence

FIX = Path(__file__).resolve().parents[1] / "fixtures"
KEYED = "Копия Keyed-Video_2608311425_0001.mov"


@pytest.fixture()
def episode(tmp_path, monkeypatch):
    src = tmp_path / "ep" / KEYED
    src.parent.mkdir()
    src.write_bytes(b"not really a 42 GB ProRes file" * 1000)
    base = tmp_path / "ep" / "MF_base.prproj"
    base.write_bytes(gzip.compress(empty_sequence(Project.load(SMALL), SEQ).to_bytes()))
    cache = tmp_path / "cache"

    d = json.loads((FIX / "transcripts" / "keyed_video_faster_whisper.json").read_text(encoding="utf-8"))
    words = tuple(Word(w["word"].strip(), w["start"], w["end"], "gigaam-v3") for s in d["segments"] for w in s["words"])
    db = np.full(int(d["duration"] / 0.01), -80.0, np.float32)
    for w in words:
        db[int(w.start / 0.01):int(w.end / 0.01) + 1] = -22
    fp = fast_fingerprint(src)
    store = JsonFileStore(cache)
    for engine in ("gigaam-v3", "parakeet-v3"):
        store.put(TranscribeEpisode.transcript_key(fp, engine),
                  Transcript(KEYED, engine, d["duration"], words).to_dict())
    store.put(TranscribeEpisode.envelope_key(fp), Envelope(0.01, db).to_dict())

    monkeypatch.setattr(FfmpegAudio, "probe", lambda self, p: MediaInfo(d["duration"], "60/1", 1920, 1080, 2, 1))
    monkeypatch.setattr(gate2, "report_dir", lambda: tmp_path / "reports")
    (tmp_path / "reports").mkdir()
    cfg = tmp_path / "ep.yaml"
    cfg.write_text(f"""
episode: МОДНАЯ ПРОПАГАНДА
profile: makashenets
script:
  export: {FIX / 'script' / 'modnaya_propaganda_gdoc_text_and_threads.json'}
  anchored: {FIX / 'script' / 'modnaya_propaganda_comments_anchored.json'}
sources: ["{src.as_posix()}"]
base_project: "{base.as_posix()}"
sequence: "{SEQ}"
cache: "{cache.as_posix()}"
""", encoding="utf-8")
    monkeypatch.delenv("MARKFLOW_GOOGLE_CREDENTIALS", raising=False)
    return cfg, base, tmp_path


def test_gate2_full_chain(episode, capsys):
    cfg, base, tmp = episode
    code = gate2.run(cfg)
    out_file = base.with_name("MF_base_MF1_draft.prproj")
    assert out_file.exists() and out_file.with_suffix(".edit_plan.json").exists()
    report = (tmp / "reports" / "gate2_ep.md").read_text(encoding="utf-8")
    printed = capsys.readouterr().out
    # structure, plan and originals must be clean; only the metrics may complain (synthetic envelope)
    for bad in ("unresolved", "duplicate", "was changed", "missing on the timeline", "not in the plan"):
        assert bad not in report, report
    info = read_sequence(Project.load(out_file), SEQ)
    assert len(info.on_track("video", 0)) >= 60 and info.duration > 0
    assert len(info.markers) > 100
    assert (tmp / "reports" / "source_map_ep.md").exists()
    frames = (tmp / "reports" / "gate3_frames_ep.txt").read_text(encoding="utf-8").splitlines()
    assert len(frames) == 5
    assert code in (0, 1) and ("\nOK" in printed or "\nFAIL" in printed)
    print(report)
    # the base project is untouched and a second run never overwrites the first result
    gate2.run(cfg)
    assert base.with_name("MF_base_MF1_draft_2.prproj").exists()


def test_gate3_on_the_draft(episode, tmp_path):
    import acceptance.gate3 as gate3

    cfg, base, tmp = episode
    gate2.run(cfg)
    out_file = base.with_name("MF_base_MF1_draft.prproj")
    frames = tmp / "frames"
    frames.mkdir()
    for k in range(5):
        (frames / f"f{k}.png").write_bytes(b"png")
    import unittest.mock as um
    with um.patch.object(gate3, "report_dir", lambda: tmp / "reports"):
        # stand-in for "Premiere opened it and saved it again": the same file
        assert gate3.run(out_file.with_suffix(".edit_plan.json"), out_file, SEQ, frames) == 0
        assert gate3.run(out_file.with_suffix(".edit_plan.json"), base, SEQ, frames) == 1  # empty timeline
    text = (tmp / "reports" / "gate3_MF_base_MF1_draft.md").read_text(encoding="utf-8")
    assert "EMPTY" in text
