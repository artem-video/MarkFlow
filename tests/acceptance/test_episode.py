from pathlib import Path

from acceptance.episode import Episode, _sources, new_output_path

REPO = Path(__file__).resolve().parents[2]


def test_reference_episode_file_loads():
    ep = Episode.load(REPO / "acceptance" / "episodes" / "modnaya_propaganda.yaml")
    assert ep.profile == "makashenets" and ep.sequence == "MF_DRAFT"
    assert ep.export.is_file() and ep.anchored.is_file()
    assert ep.asr_engines == ("gigaam-v3",)
    assert ep.base_project == REPO / "templates" / "makashenets" / "MF_base.prproj"
    assert ep.output_dir is not None and "MarkFlow" in str(ep.output_dir)


def test_glob_prefers_the_shallowest_file(tmp_path):
    (tmp_path / "EXPORT" / "BLooP").mkdir(parents=True)
    (tmp_path / "EXPORT" / "BLooP" / "Копия 20260828_B0002.mp4").write_bytes(b"x")
    (tmp_path / "Копия 20260828_B0002.MP4").write_bytes(b"x")
    found = _sources([str(tmp_path / "**" / "Копия 20260828_B000*.MP4")])
    assert found == (tmp_path / "Копия 20260828_B0002.MP4",)


def test_source_globs_and_dedupe(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    for name in ("Копия 20260828_B0002.MP4", "Копия 20260828_B0003.MP4"):
        (tmp_path / "a" / "b" / name).write_bytes(b"x")
    (tmp_path / "a" / "Копия 20260828_B0002.MP4").write_bytes(b"x")
    found = _sources([str(tmp_path / "**" / "Копия 20260828_B000*.MP4"), str(tmp_path / "missing.wav")])
    assert sorted(p.name for p in found) == ["missing.wav", "Копия 20260828_B0002.MP4", "Копия 20260828_B0003.MP4"]


def test_output_name_never_existing(tmp_path):
    base = tmp_path / "MF_base.prproj"
    assert new_output_path(base).name == "MF_base_MF1_draft.prproj"
    new_output_path(base).write_bytes(b"x")
    assert new_output_path(base).name == "MF_base_MF1_draft_2.prproj"
