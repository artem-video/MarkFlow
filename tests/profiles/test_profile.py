from pathlib import Path

import pytest
import yaml

from markflow.domain.edit_plan import LabelColor
from markflow.domain.script_model import DEFAULT_CUES, BlockKind, parse_script
from markflow.infra.google.docs_reader import load_connector_export
from markflow.profiles.loader import PROFILES_DIR, ProfileError, list_profiles, load_profile, parse_profile

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "script"


@pytest.fixture(scope="module")
def profile():
    return load_profile("makashenets")


def test_profile_is_listed_and_has_style_md():
    assert "makashenets" in list_profiles()
    assert (PROFILES_DIR / "makashenets" / "STYLE.md").read_text(encoding="utf-8").startswith("# Макашенец")


def test_phantom_cut_settings(profile):
    assert (profile.cut.silence_db, profile.cut.max_pause_s, profile.cut.handle_s) == (-60, 0.5, 0.04)
    assert profile.cut.take_policy == "last" and profile.cut.keep_improv


def test_track_layout_of_the_real_episode(profile):
    v, a = profile.tracks.video, profile.tracks.audio
    assert (v.talking_head, v.sizes, v.lives) == (0, 1, 2)
    assert a.voice == [0, 1] and a.lives == [2, 3] and a.bleep == [7]


def test_colors_are_premiere_labels_and_distinct(profile):
    marker_colors = [profile.markers.check_color, profile.markers.script_comment_color,
                     profile.markers.command_color, profile.markers.live_missing_color]
    assert all(isinstance(c, LabelColor) for c in marker_colors)
    assert len(set(marker_colors)) == len(marker_colors)
    assert profile.colors.improv_meaningful != profile.colors.improv_funny
    assert profile.markers.check_name == "ПРОВЕРИТЬ"


def test_style_rules_from_the_guide(profile):
    assert profile.style.bleep.mode == "partial"
    assert "Пыпа" in profile.style.aliases["Путин"]
    assert profile.style.max_technique_repeats == 3
    assert any("Robert B. Weide" in b for b in profile.style.banned)
    assert profile.lives.max_height == 1440


def test_profile_cues_parse_the_real_script_like_defaults(profile):
    raw = load_connector_export(FIX / "modnaya_propaganda_gdoc_text_and_threads.json")
    by_profile = parse_script(raw, profile.script.vocabulary())
    by_default = parse_script(raw, DEFAULT_CUES)
    assert [b.kind for b in by_profile.blocks] == [b.kind for b in by_default.blocks]
    assert set(profile.script.cues) == set(BlockKind) - {BlockKind.DIRECTION}


def _text(**changes):
    data = yaml.safe_load((PROFILES_DIR / "makashenets" / "profile.yaml").read_text(encoding="utf-8"))
    for dotted, value in changes.items():
        node = data
        *path, last = dotted.split("__")
        for key in path:
            node = node[key]
        node[last] = value
    return yaml.safe_dump(data, allow_unicode=True)


@pytest.mark.parametrize("change,msg", [
    (dict(cut__silence_db=10), "silence_db"),
    (dict(cut__take_policy="first"), "take_policy"),
    (dict(markers__check_color="Pink"), "check_color"),
    (dict(tracks__audio__lives=[1, 2]), "audio track roles overlap"),
    (dict(cut__typo_key=1), "typo_key"),
    (dict(style__bleep__mode="loud"), "mode"),
])
def test_bad_profiles_are_rejected_with_a_clear_reason(change, msg):
    with pytest.raises(ProfileError, match=msg):
        parse_profile(_text(**change))


def test_missing_profile_and_broken_yaml(tmp_path):
    with pytest.raises(ProfileError, match="no profile"):
        load_profile("varlamov", root=tmp_path)
    with pytest.raises(ProfileError, match="not valid YAML"):
        parse_profile("a: [1, 2")
    with pytest.raises(ProfileError, match="mapping"):
        parse_profile("- 1")


def test_new_channel_needs_only_a_folder(tmp_path):
    (tmp_path / "shtefanov").mkdir()
    text = _text(channel__id="shtefanov", channel__name="Штефанов")
    (tmp_path / "shtefanov" / "profile.yaml").write_text(text, encoding="utf-8")
    assert load_profile("shtefanov", root=tmp_path).channel.name == "Штефанов"
    assert list_profiles(tmp_path) == ["shtefanov"]
