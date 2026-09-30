"""Stage 3.1–3.2 on projects saved by real Premiere 26 (tests/fixtures/prproj)."""

import gzip
from pathlib import Path

import pytest

from markflow.domain.edit_plan import (
    Clip, ClipReason, EditPlan, LabelColor, Marker, MarkerKind, Sequence, Source, SourceKind, TextLayer,
)
from markflow.infra.prproj.project import AUDIO_MEDIA_TYPE, VIDEO_MEDIA_TYPE, Project
from markflow.infra.prproj.reader import read_sequence
from markflow.infra.prproj.validator import plan_problems, structure_problems, untouched_problems
from markflow.infra.prproj.writer import WriteError, write_into, write_plan
from markflow.shared.timecode import seconds_to_ticks as t

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "prproj"
SMALL = FIX / "premiere_saved_small_6seq.prproj"
REAL = FIX / "premiere_saved_real_episode_full.prproj"
EP = "C:\\Users\\Artem\\Videos\\Макашенец\\МОДНАЯ ПРОПАГАНДА\\"
SEQ = "МОДНАЯ ПРОПАГАНДА — AutoCut Test"
F60 = 4_233_600_000


def empty_sequence(project: Project, name: str) -> Project:
    """Test helper: the fixture has no empty sequence yet (the real template comes from stage 0.3)."""
    seq = project.sequence(name)
    for mt in (VIDEO_MEDIA_TYPE, AUDIO_MEDIA_TYPE):
        for track in project.tracks(seq, mt):
            items = track.find("ClipTrack/ClipItems/TrackItems")
            if items is not None:
                items.getparent().remove(items)
    links = seq.find("PersistentGroupContainer/LinkContainer/Links")
    if links is not None:
        for link in list(links):
            links.remove(link)
    raw = project.to_bytes()
    return Project.from_bytes(raw, "emptied")


def frames(n):
    return n * F60


def plan(**over):
    base = dict(
        episode="МОДНАЯ ПРОПАГАНДА", profile="makashenets",
        sequence=Sequence(name=SEQ, fps="60", width=1920, height=1080),
        sources=(
            Source(id="kv", path=EP + "Копия Keyed-Video_2608311425_0001.mov", kind=SourceKind.PICKUP, fps="60",
                   duration=t(1731)),
            Source(id="b1", path=EP + "Копия 20260828_B0001.MP4", kind=SourceKind.MAIN, fps="50", duration=t(600)),
            Source(id="vo", path=EP.replace("МОДНАЯ ПРОПАГАНДА\\", "МОДНАЯ ПРОПАГАНДА\\") +
                   "VO_MAKASHENETS_20260904.wav", kind=SourceKind.VOICEOVER, fps="60", duration=t(120),
                   has_video=False, audio_channels=2),
        ),
        clips=(
            Clip(id="c1", source_id="kv", source_in=frames(1800), source_out=frames(1800 + 300), start=0,
                 video_track=0, audio_tracks=(0, 1)),
            Clip(id="c2", source_id="b1", source_in=frames(600), source_out=frames(600 + 120), start=frames(300),
                 video_track=0, audio_tracks=(0, 1), reason=ClipReason.IMPROV_FUNNY, color=LabelColor.MAGENTA),
            Clip(id="c3", source_id="vo", source_in=0, source_out=frames(240), start=frames(420), audio_tracks=(0,)),
        ),
        markers=(Marker(id="m1", start=frames(300), name="ПРОВЕРИТЬ: дубль", comment="сверить", kind=MarkerKind.CHECK),),
        text_layers=(TextLayer(id="t1", start=frames(660), duration=frames(300), video_track=0,
                               text="ЛАЙВ 001\nhttps://youtu.be/abc"),),
    )
    base.update(over)
    return EditPlan(**base)


@pytest.fixture(scope="module")
def base():
    return empty_sequence(Project.load(SMALL), SEQ)


def test_fixtures_pass_structure_checks():
    assert structure_problems(Project.load(SMALL)) == []


def test_real_episode_passes_structure_checks():
    project = Project.load(REAL)
    assert len(project.sequences()) == 17
    assert structure_problems(project) == []


def test_reader_on_fixture():
    info = read_sequence(Project.load(SMALL), SEQ)
    assert (info.frame_ticks, info.width, info.height, info.video_tracks, info.audio_tracks) == (F60, 1920, 1080, 1, 2)
    assert len(info.on_track("video", 0)) == 2 and len(info.on_track("audio", 1)) == 2
    assert info.items[0].media_path.endswith("Копия Keyed-Video_2608311425_0001.mov")
    assert info.markers and info.markers[0].name == "🎮 HUD / ВЫБОР СКИНА"


def test_write_plan_passes_all_checks(base):
    out = Project.from_bytes(base.to_bytes())
    write_into(out, plan(), SEQ)
    again = Project.from_bytes(out.to_bytes())  # what Premiere would parse
    assert structure_problems(again) == []
    assert plan_problems(again, plan(), SEQ, base) == []
    assert untouched_problems(base, again, SEQ) == []
    info = read_sequence(again, SEQ)
    v1 = info.on_track("video", 0)
    assert [(i.start, i.end, i.in_point) for i in v1] == [(0, frames(300), frames(1800)),
                                                         (frames(300), frames(420), frames(600))]
    assert v1[1].label == "BE.Prefs.LabelColors.11"
    a1 = info.on_track("audio", 0)
    assert len(a1) == 3 and a1[2].media_path.endswith("VO_MAKASHENETS_20260904.wav")
    assert {"ПРОВЕРИТЬ: дубль", "ЛАЙВ 001"} <= {m.name for m in info.markers}


def test_links_join_video_and_both_channels(base):
    out = write_into(Project.from_bytes(base.to_bytes()), plan(), SEQ)
    links = out.objects("Link")
    new_links = [l for l in links if l.get("ObjectID") not in base.by_id]
    assert [len(l.findall("TrackItemGroup/TrackItems/TrackItem")) for l in new_links] == [3, 3]  # vo is alone
    audio_item = out.by_id[new_links[0].findall("TrackItemGroup/TrackItems/TrackItem")[2].get("ObjectRef")]
    clip = out.ref(out.ref(audio_item.find("ClipTrackItem/SubClip")).find("Clip"))
    assert clip.findtext("SecondaryIndex") == "1"
    assert out.ref(clip.find("SecondaryContents/SecondaryContentItem")).findtext("ChannelIndex") == "1"


def test_write_plan_to_a_new_file(base, tmp_path):
    base_file = tmp_path / "base.prproj"
    original = gzip.compress(base.to_bytes())
    base_file.write_bytes(original)
    out = tmp_path / "base_MF1_draft.prproj"
    write_plan(base_file, plan(), out, SEQ)
    assert out.read_bytes()[:2] == b"\x1f\x8b"
    assert base_file.read_bytes() == original  # untouched
    with pytest.raises(WriteError, match="never overwrites"):
        write_plan(base_file, plan(), out, SEQ)
    with pytest.raises(WriteError, match="overwrite the base"):
        write_plan(base_file, plan(), base_file, SEQ)


def test_writer_refusals(base):
    with pytest.raises(WriteError, match="not empty"):
        write_into(Project.load(SMALL), plan(), SEQ)
    missing = plan(sources=plan().sources[:2] + (Source(id="vo", path="D:/нет/такого.wav", kind=SourceKind.VOICEOVER,
                                                          fps="60", duration=t(120), has_video=False),))
    with pytest.raises(WriteError, match="import these files"):
        write_into(Project.from_bytes(base.to_bytes()), missing, SEQ)
    with pytest.raises(WriteError, match="frame rate"):
        write_into(Project.from_bytes(base.to_bytes()), plan(sequence=Sequence(name=SEQ, fps="25", width=1920,
                                                                               height=1080)), SEQ)
    wide = plan(clips=(Clip(id="c1", source_id="kv", source_in=0, source_out=frames(10), start=0, video_track=3),))
    with pytest.raises(WriteError, match="video tracks"):
        write_into(Project.from_bytes(base.to_bytes()), wide, SEQ)


def test_validator_catches_broken_projects(base):
    out = write_into(Project.from_bytes(base.to_bytes()), plan(), SEQ)
    raw = out.to_bytes()
    # 1. dangling reference
    broken = Project.from_bytes(raw.replace(b'<SubClip ObjectRef="', b'<SubClip ObjectRef="9', 1))
    assert any("unresolved" in p for p in structure_problems(broken))
    # 2. duplicate id
    dup = Project.from_bytes(raw)
    extra = dup.objects("Marker")[-1]
    import copy
    dup.root.append(copy.deepcopy(extra))
    assert any("duplicate ObjectID" in p for p in structure_problems(Project.from_bytes(dup.to_bytes())))
    # 3. an original clip was changed
    changed = Project.from_bytes(raw.replace("<Name>Копия 20260828_B0003.MP4</Name>".encode(),
                                             b"<Name>renamed</Name>", 1))
    assert any("was changed" in p for p in untouched_problems(base, changed, SEQ))
    # 4. timeline does not match the plan (an empty timeline = FAIL)
    assert any("items on the timeline" in p for p in plan_problems(base, plan(), SEQ))
    # 5. overlap
    ov = Project.from_bytes(raw)
    items = ov.track_items(ov.tracks(ov.sequence(SEQ), VIDEO_MEDIA_TYPE)[0])
    items[1].find("ClipTrackItem/TrackItem/Start").text = str(frames(100))
    items[1].find("ClipTrackItem/TrackItem/End").text = str(frames(220))
    assert any("overlap" in p for p in structure_problems(ov))
