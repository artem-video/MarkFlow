import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from markflow.domain.edit_plan import (
    SCHEMA_VERSION, Clip, ClipReason, EditPlan, LabelColor, Marker, MarkerKind, PlanError, Sequence, Source,
    SourceKind, TextLayer, from_json, migrate, to_json,
)
from markflow.shared.timecode import seconds_to_ticks as t

SCHEMA_LOCK = Path(__file__).resolve().parents[1] / "fixtures" / "schema" / f"edit_plan_v{SCHEMA_VERSION}.sha256"


def _plan(**over):
    base = dict(
        episode="МОДНАЯ ПРОПАГАНДА",
        profile="makashenets",
        sequence=Sequence(name="MF1", fps="60", width=1920, height=1080),
        sources=(
            Source(id="kv", path="C:/Видео/Keyed-Video.mov", kind=SourceKind.MAIN, fps="60", duration=t(1731)),
            Source(id="vo", path="C:/Видео/VO.wav", kind=SourceKind.VOICEOVER, fps="60", duration=t(60),
                   has_video=False, audio_channels=1),
        ),
        clips=(
            Clip(id="c1", source_id="kv", source_in=t(10), source_out=t(14), start=0,
                 video_track=0, audio_tracks=(0, 1), script_ref="B001"),
            Clip(id="c2", source_id="kv", source_in=t(20), source_out=t(22), start=t(4),
                 video_track=0, audio_tracks=(0, 1), reason=ClipReason.IMPROV_FUNNY, color=LabelColor.MAGENTA),
            Clip(id="c3", source_id="vo", source_in=0, source_out=t(3), start=t(6), audio_tracks=(0,)),
        ),
        markers=(Marker(id="m1", start=t(4), name="ПРОВЕРИТЬ", kind=MarkerKind.CHECK, color=LabelColor.ROSE),),
        text_layers=(TextLayer(id="tl1", start=t(9), duration=t(2), video_track=6, text="ЛАЙВ 001 не скачан"),),
    )
    base.update(over)
    return EditPlan(**base)


def test_valid_plan_and_duration():
    plan = _plan()
    assert plan.duration == t(11)
    assert [c.id for c in plan.clips_on_audio_track(0)] == ["c1", "c2", "c3"]


def test_json_round_trip_is_lossless():
    plan = _plan()
    again = from_json(to_json(plan))
    assert again == plan
    assert "МОДНАЯ ПРОПАГАНДА" in to_json(plan)


def test_overlap_on_a_track_is_rejected():
    clips = _plan().clips + (
        Clip(id="c4", source_id="kv", source_in=t(30), source_out=t(33), start=t(2), video_track=0),
    )
    with pytest.raises(ValidationError, match="V1: c1 overlaps c4"):
        _plan(clips=clips)


def test_same_time_on_different_tracks_is_fine():
    clips = _plan().clips + (
        Clip(id="c4", source_id="kv", source_in=t(30), source_out=t(33), start=t(1), video_track=1),
    )
    assert len(_plan(clips=clips).clips) == 4


@pytest.mark.parametrize("bad,msg", [
    (dict(source_in=t(5), source_out=t(5)), "source_out must be after"),
    (dict(video_track=None, audio_tracks=()), "needs a video track"),
    (dict(audio_tracks=(0, 0)), "distinct"),
])
def test_clip_rules(bad, msg):
    args = dict(id="x", source_id="kv", source_in=0, source_out=t(1), start=0, video_track=0, audio_tracks=(0,))
    args.update(bad)
    with pytest.raises(ValidationError, match=msg):
        Clip(**args)


def test_unknown_source_duplicate_ids_and_out_of_range():
    bad = _plan().clips + (
        Clip(id="c1", source_id="nope", source_in=0, source_out=t(1), start=t(50), video_track=0),
        Clip(id="c9", source_id="kv", source_in=t(1730), source_out=t(1740), start=t(60), video_track=0),
        Clip(id="c10", source_id="vo", source_in=0, source_out=t(1), start=t(70), video_track=0),
    )
    with pytest.raises(ValidationError) as err:
        _plan(clips=bad)
    text = str(err.value)
    assert "duplicate ids" in text and "unknown source nope" in text
    assert "beyond source duration" in text and "has no video" in text


def test_unknown_fields_are_rejected():
    data = json.loads(to_json(_plan()))
    data["surprise"] = 1
    with pytest.raises(ValidationError):
        from_json(json.dumps(data))


def test_plan_is_immutable():
    with pytest.raises(ValidationError):
        _plan().episode = "x"


# ---------- versioning ----------

def test_schema_is_locked_for_this_version():
    """Changing the plan models without SCHEMA_VERSION + 1 and a migration must fail here.

    If you changed the schema on purpose: bump SCHEMA_VERSION, add MIGRATIONS[old], add a migration test,
    then write the new hash to tests/fixtures/schema/edit_plan_v<new>.sha256.
    """
    assert SCHEMA_LOCK.read_text().strip() == schema_fingerprint()


def schema_fingerprint() -> str:
    """Field names, types and defaults of every plan model and enum — independent of the pydantic version."""
    import enum

    from markflow.domain import edit_plan

    shape = {}
    for name, obj in sorted(vars(edit_plan).items()):
        if isinstance(obj, type) and issubclass(obj, enum.Enum) and obj.__module__ == edit_plan.__name__:
            shape[name] = [m.value for m in obj]
        elif isinstance(obj, type) and issubclass(obj, edit_plan._Model) and obj is not edit_plan._Model:
            shape[name] = {f: [str(i.annotation), repr(i.default)] for f, i in obj.model_fields.items()}
    return hashlib.sha256(json.dumps(shape, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def test_migration_chain_runs_in_order():
    steps = {
        1: lambda d: {"schema_version": d["schema_version"], "renamed": d["old"]},
        2: lambda d: {**d, "added": True},
    }
    out = migrate({"schema_version": 1, "old": 5}, migrations=steps, target=3)
    assert out == {"schema_version": 3, "renamed": 5, "added": True}


def test_migration_errors():
    with pytest.raises(PlanError, match="no integer schema_version"):
        migrate({})
    with pytest.raises(PlanError, match="newer"):
        migrate({"schema_version": SCHEMA_VERSION + 1})
    with pytest.raises(PlanError, match="no migration"):
        migrate({"schema_version": 0}, migrations={}, target=1)


def test_from_json_rejects_garbage():
    with pytest.raises(PlanError):
        from_json("{not json")
