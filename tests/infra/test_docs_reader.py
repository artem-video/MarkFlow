"""Stage 1.2 on the real script «МОДНАЯ ПРОПАГАНДА» (fixtures saved in stage 0.7) + the Drive API reader."""

import re
from pathlib import Path

import pytest

from markflow.domain.script_model import BlockKind, RawDoc, parse_script, select_part
from markflow.infra.google.docs_reader import GoogleDocsReader, load_connector_export
from markflow.shared.text_norm import find_urls, normalize, strip_markdown, without_links

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "script"
TEXT = FIX / "modnaya_propaganda_gdoc_text_and_threads.json"
ANCHORED = FIX / "modnaya_propaganda_comments_anchored.json"


@pytest.fixture(scope="module")
def raw():
    return load_connector_export(TEXT, ANCHORED)


@pytest.fixture(scope="module")
def script(raw):
    return parse_script(raw)


def test_connector_export_comments(raw):
    open_ = [c for c in raw.comments if not c.resolved]
    assert len(open_) == 140 and len(raw.comments) == 146
    assert sum(len(c.replies) for c in open_) >= 50
    assert raw.title == "МОЙ ЮТУБ_МОДНАЯ ПРОПАГАНДА"


def test_script_structure(script):
    kinds = [b.kind for b in script.blocks]
    assert kinds.count(BlockKind.LIVE) == 159
    assert kinds.count(BlockKind.STANDUP) >= 150
    assert kinds.count(BlockKind.PART) == 1
    assert script.blocks[0].lines == ("Что-то вышло из моды…",)
    assert len(script.appendix) == 11 and script.appendix[0].title == "ЕБКОВ И АНТОНОВ"
    assert script.reserve and all(b.in_reserve for b in script.reserve)


def test_first_live_is_complete(script):
    live = script.blocks[1]
    assert (live.kind, live.number) == (BlockKind.LIVE, "001")
    assert live.links == ("https://rutube.ru/video/6b2ad8de74679bf44f32ff94c4bae080/",)
    assert (live.clocks[0].start, live.clocks[0].end) == (4513.0, 4516.0)


def _all_text(block) -> str:
    parts = [block.header, *block.lines, *block.notes, *block.links, *(c.words for c in block.clocks)]
    return normalize(" ".join(parts))


def _script_lines(raw: RawDoc) -> list[str]:
    clean = re.sub(r"<comment_(start|end) id=[^>]+>", "", raw.markdown)
    body = re.split(r"(?m)^# ", clean)[1]  # the '# сценарий' section
    lines = [strip_markdown(l) for l in body.split("\n")[1:]]
    return [l for l in lines if normalize(l)]


def _no_digits(text: str) -> str:
    text = re.sub(r"(\d)(?=[^\d\s])|(?<=[^\d\s])(?=\d)", r"\1 ", normalize(text))  # '13:42обороты'
    return " ".join(w for w in text.split() if not w.isdigit())


def test_nothing_is_lost(raw, script):
    """Every line of the script section ends up in some block (main or reserve).

    Timecode digits are compared as numbers (Clock.start/end), so only words are checked here.
    """
    everything = " | ".join(_no_digits(_all_text(b)) for b in script.blocks + script.reserve)
    lost = []
    for line in _script_lines(raw):
        if normalize(line) in {"конец", "резерв"}:
            continue
        probe = _no_digits(" ".join(find_urls(line)) if not normalize(without_links(line)) else line)
        if probe and probe not in everything:
            lost.append(line)
    assert lost == []


def test_every_open_comment_with_anchor_is_placed(script):
    open_ = script.open_comments
    placed = [c for c in open_ if c.anchored]
    no_anchor = [c for c in open_ if not c.anchor_text]
    assert len(placed) + len(no_anchor) == len(open_) == 140
    assert script.warnings == ()


def test_text_route_equals_mark_route(raw, script):
    """The Drive API markdown export has no comment marks: anchoring by text must give the same result."""
    api_like = RawDoc(raw.title, re.sub(r"<comment_(start|end) id=[^>]+>", "", raw.markdown), raw.comments)
    assert [c.block_ids for c in parse_script(api_like).comments] == [c.block_ids for c in script.comments]


def test_doubtful_places_are_marked(script):
    flagged = [b for b in script.blocks if b.checks]
    assert 0 < len(flagged) < 40
    assert any("live without a link" in b.checks for b in flagged)


def test_part_two_selection(script):
    part_at = next(i for i, b in enumerate(script.blocks) if b.kind == BlockKind.PART)
    first_standup = next(b for b in script.blocks[part_at:] if b.kind == BlockKind.STANDUP)
    part2 = select_part(script, first_words=first_standup.lines[0][:60])
    assert part2.blocks[0].id == first_standup.id
    assert part2.blocks[-1].id == script.blocks[-1].id


# ---------- Drive API route with a fake service ----------

class _Call:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class _FakeDrive:
    def __init__(self):
        self.pages = [
            {"comments": [
                {"id": "a", "author": {"displayName": "Макашенец"}, "content": "Даем кадры",
                 "quotedFileContent": {"value": "Вторая строка"}, "resolved": False,
                 "replies": [{"content": "005"}, {"content": "", "deleted": True}]},
                {"id": "gone", "deleted": True, "content": "x"},
            ], "nextPageToken": "p2"},
            {"comments": [{"id": "b", "author": {"displayName": "Артём"}, "content": "ок", "resolved": True}]},
        ]
        self.calls = []

    def files(self):
        return self

    def comments(self):
        return self

    def get(self, **kw):
        return _Call({"name": "МОЙ ЮТУБ_МИНИ"})

    def export(self, **kw):
        assert kw["mimeType"] == "text/markdown"
        return _Call("**СТЕНДАП**\nПервая строка.\nВторая строка.\n".encode("utf-8"))

    def list(self, **kw):
        self.calls.append(kw)
        return _Call(self.pages[len(self.calls) - 1])


def test_api_reader_with_fake_drive():
    drive = _FakeDrive()
    raw = GoogleDocsReader(drive).read("doc-id")
    assert raw.title == "МОЙ ЮТУБ_МИНИ"
    assert [c.id for c in raw.comments] == ["a", "b"]
    assert raw.comments[0].anchor_text == "Вторая строка" and raw.comments[0].replies == ("005",)
    assert raw.comments[1].resolved
    assert drive.calls[1]["pageToken"] == "p2"
    s = parse_script(raw)
    assert s.comments[0].block_ids == ("B001",)


def test_human_report_lists_checks_and_lives(script):
    from tools.script_report import render

    report = render(script)
    assert report.startswith("# Разбор сценария «МОЙ ЮТУБ_МОДНАЯ ПРОПАГАНДА»")
    assert "## ПРОВЕРИТЬ" in report and "лайв без ссылки" in report
    assert "https://rutube.ru/video/6b2ad8de74679bf44f32ff94c4bae080/ | 1:15:13–1:15:16" in report
