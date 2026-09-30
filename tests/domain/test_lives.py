from markflow.domain.script_model import BlockKind, Clock, ScriptBlock
from markflow.domain.timeline import LIVE_DEFAULT_S, live_segments
from markflow.shared.links import live_key


def _block(*clocks: Clock) -> ScriptBlock:
    return ScriptBlock(id="B1", kind=BlockKind.LIVE, header="ЛАЙВ", clocks=tuple(clocks))


def test_same_video_behind_different_links_has_one_key():
    keys = {live_key(u) for u in (
        "https://www.youtube.com/watch?v=PuKuothgmT8&t=347s", "https://youtu.be/PuKuothgmT8?si=5Nv_sb9x8FcGJ4t-",
        "http://youtube.com/watch?v=PuKuothgmT8", "https://www.youtube.com/shorts/PuKuothgmT8")}
    assert keys == {"youtube:PuKuothgmT8"}
    assert live_key("https://rutube.ru/video/abc/?r=wd") == live_key("https://rutube.ru/video/abc/")


def test_range_and_single_moment_segments_are_clipped_to_the_file():
    segs = live_segments(_block(Clock(75.0, 80.0), Clock(26.0, None), Clock(3000.0, 3010.0)), total=600.0)
    assert segs == [(75.0, 80.0), (26.0, 26.0 + LIVE_DEFAULT_S)]  # the third starts after the end of the file


def test_no_timecodes_means_the_start_of_the_file():
    assert live_segments(_block(), total=600.0) == [(0.0, LIVE_DEFAULT_S)]
