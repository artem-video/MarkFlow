"""The writer creates master clips itself when the base is the empty template (PLAN 3.2, stage 0.3)."""

from pathlib import Path

from markflow.domain.edit_plan import Clip, EditPlan, Marker, MarkerKind, Sequence, Source, SourceKind
from markflow.infra.prproj.media import MediaSpec, fourcc
from markflow.infra.prproj.project import Project
from markflow.infra.prproj.reader import read_sequence
from markflow.infra.prproj.validator import plan_problems, structure_problems, untouched_problems
from markflow.infra.prproj.writer import write_into, write_plan
from markflow.shared.timecode import seconds_to_ticks as t

TEMPLATE = Path(__file__).resolve().parents[3] / "templates" / "makashenets" / "MF_base.prproj"
EP = "C:\\Users\\Artem\\Videos\\Макашенец\\МОДНАЯ ПРОПАГАНДА\\"
F2997 = 8_475_667_200

MEDIA = {
    EP + "Копия 20260828_B0001.MP4": MediaSpec(EP + "Копия 20260828_B0001.MP4", 3891.3875, "30000/1001",
                                                3840, 2160, 2, 48000, "avc1"),
    EP + "Копия Keyed-Video_2608311425_0001.mov": MediaSpec(EP + "Копия Keyed-Video_2608311425_0001.mov",
                                                            1731.516667, "60/1", 1920, 1080, 2, 48000, "apcs"),
    EP + "VO_MAKASHENETS_20260904.wav": MediaSpec(EP + "VO_MAKASHENETS_20260904.wav", 171.6, None, None, None, 2),
}


def plan() -> EditPlan:
    f = F2997
    return EditPlan(
        episode="МОДНАЯ ПРОПАГАНДА", profile="makashenets",
        sequence=Sequence(name="MF_DRAFT", fps="30000/1001", width=3840, height=2160),
        sources=(
            Source(id="b1", path=EP + "Копия 20260828_B0001.MP4", kind=SourceKind.MAIN, fps="30000/1001",
                   duration=t(3891)),
            Source(id="kv", path=EP + "Копия Keyed-Video_2608311425_0001.mov", kind=SourceKind.PICKUP, fps="60/1",
                   duration=t(1731)),
            Source(id="vo", path=EP + "VO_MAKASHENETS_20260904.wav", kind=SourceKind.VOICEOVER, fps="30000/1001",
                   duration=t(171), has_video=False, audio_channels=2),
        ),
        clips=(
            Clip(id="c1", source_id="b1", source_in=100 * f, source_out=400 * f, start=0, video_track=0,
                 audio_tracks=(0, 1)),
            Clip(id="c2", source_id="kv", source_in=0, source_out=150 * f, start=300 * f, video_track=0,
                 audio_tracks=(0, 1)),
            Clip(id="c3", source_id="vo", source_in=0, source_out=90 * f, start=450 * f, audio_tracks=(0, 1)),
        ),
        markers=(Marker(id="m1", start=300 * f, name="ПРОВЕРИТЬ", comment="x", kind=MarkerKind.CHECK),),
    )


def test_fourcc():
    assert fourcc("avc1") == 1635148593 and fourcc("apcs") == 1634755443 and fourcc(None) is None


def test_template_is_empty_and_exact_ntsc():
    base = Project.load(TEMPLATE)
    seq = base.sequence("MF_DRAFT")
    assert base.frame_ticks(seq) == F2997
    assert base.master_clips_by_path() == {}


def test_writer_imports_sources_into_empty_template():
    base = Project.load(TEMPLATE)
    out = write_into(Project.load(TEMPLATE), plan(), "MF_DRAFT", MEDIA)
    out = Project.from_bytes(out.to_bytes(), "out")
    assert structure_problems(out) == []
    assert plan_problems(out, plan(), "MF_DRAFT", base) == []
    assert untouched_problems(base, out, "MF_DRAFT") == []
    assert len(out.master_clips_by_path()) == 3
    info = read_sequence(out, "MF_DRAFT")
    assert len(info.items) == 2 + 6  # 2 video items + 3 clips x 2 audio channels
    # every new master clip is in the root bin
    root = out.objects("RootProjectItem")[0]
    assert len(root.findall("ProjectItemContainer/Items/Item")) == 4


def test_write_plan_file(tmp_path):
    out = tmp_path / "MF_base_MF1_draft.prproj"
    write_plan(TEMPLATE, plan(), out, "MF_DRAFT", MEDIA)
    assert structure_problems(Project.load(out)) == []
