"""Script model: a Google Doc script (markdown export + comments) -> ordered blocks.

Pure: receives a RawDoc (built by infra/google/docs_reader), returns a Script.
Cue words (СТЕНДАП, ЛАЙВ, ...) come from the channel profile, so a new channel needs no code.

Doc layout seen on Makashenets (МОДНАЯ ПРОПАГАНДА):
    # сценарий                 <- first section = the script
    **СТЕНДАП** / text lines   <- host speaks
    **001 ЛАЙВ ...** / link / **1:15:13 words — 1:15:16**   <- video insert
    ***КОНЕЦ***                <- end of the script; what follows is РЕЗЕРВ (reserve)
    # ЕБКОВ И АНТОНОВ ...      <- further sections = transcripts of the lives (appendix)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from enum import Enum

from rapidfuzz import fuzz

from markflow.shared.text_norm import find_urls, normalize, strip_markdown, without_links
from markflow.shared.timecode import find_clocks

_COMMENT_MARK = re.compile(r"<comment_(start|end) id=([^>]+)>")
_NUMBER_PREFIX = re.compile(r"^(\d{1,4})[\s.:)-]*")


class ScriptError(ValueError):
    pass


class BlockKind(str, Enum):
    STANDUP = "standup"      # host speaks on camera
    LIVE = "live"            # video insert (link + timecodes)
    QUOTE = "quote"          # on-screen quote (post, article)
    VOICEOVER = "voiceover"  # host text recorded as VO
    INSERT = "insert"        # "insert the separately recorded standup here" + link
    BUTT = "butt"            # ВСТЫК: hard cut instruction
    DIRECTION = "direction"  # any other instruction for the editor
    PART = "part"            # 'ЧАСТЬ 2': the episode is split into parts


# ---------- input (built by infra) ----------

@dataclass(frozen=True)
class RawComment:
    id: str
    author: str
    text: str
    anchor_text: str | None = None   # quoted text the comment is attached to
    anchor_id: str | None = None     # id of <comment_start id=..> in the markdown, when the export has it
    resolved: bool = False
    replies: tuple[str, ...] = ()


@dataclass(frozen=True)
class RawDoc:
    title: str
    markdown: str
    comments: tuple[RawComment, ...] = ()


@dataclass(frozen=True)
class CueVocabulary:
    """Header words per block kind, matched in UPPER CASE at the start of a line (after an optional number)."""

    kinds: dict[BlockKind, tuple[str, ...]]
    end_words: tuple[str, ...] = ("КОНЕЦ",)
    reserve_words: tuple[str, ...] = ("РЕЗЕРВ",)

    def match(self, header: str) -> tuple[BlockKind, str] | None:
        """'008 ЛАЙВ: АНТОНОВ' -> (LIVE, 'ЛАЙВ'). Longest cue wins (ТЕКСТ ВЕДУЩЕГО before ТЕКСТ)."""
        best: tuple[BlockKind, str] | None = None
        for kind, cues in self.kinds.items():
            for cue in cues:
                if header.startswith(cue) and (len(header) == len(cue) or not header[len(cue)].isalnum()):
                    if best is None or len(cue) > len(best[1]):
                        best = (kind, cue)
        return best


DEFAULT_CUES = CueVocabulary(
    kinds={
        BlockKind.STANDUP: ("СТЕНДАП", "ТЕКСТ ВЕДУЩЕГО"),
        BlockKind.LIVE: ("ЛАЙВ",),
        BlockKind.QUOTE: ("ЦИТАТА",),
        BlockKind.VOICEOVER: ("ЗАКАДРОВЫЙ ТЕКСТ", "ЗАКАДРОВЫЙ", "ЗАКАДР"),
        BlockKind.PART: ("ЧАСТЬ",),
        BlockKind.INSERT: ("СЮДА ВСТРАИВАЕМ",),
        BlockKind.BUTT: ("ВСТЫК",),
    }
)


# ---------- output ----------

@dataclass(frozen=True)
class Clock:
    """A timecode range inside a live: '1:15:13 я подготовлюсь — 1:15:16' or '16:06 государство — 16:28 действия'."""

    start: float
    end: float | None
    start_words: str = ""  # what is said at `start`
    end_words: str = ""    # what is said just before `end`

    @property
    def words(self) -> str:
        return " ".join(w for w in (self.start_words, self.end_words) if w)


@dataclass(frozen=True)
class Highlight:
    comment_id: str
    text: str


@dataclass(frozen=True)
class ScriptBlock:
    id: str
    kind: BlockKind
    header: str                      # visible header line ('' for implicit blocks)
    number: str | None = None        # '001' from '001 ЛАЙВ'
    label: str = ""                  # rest of the header: 'АНТОНОВ', '(в начале)'
    lines: tuple[str, ...] = ()      # visible body lines (spoken text, quote text, direction text)
    notes: tuple[str, ...] = ()      # editor instructions written inside a live/quote block
    links: tuple[str, ...] = ()
    clocks: tuple[Clock, ...] = ()
    comment_ids: tuple[str, ...] = ()
    highlights: tuple[Highlight, ...] = ()
    implicit: bool = False           # no header in the doc: kind was inferred
    checks: tuple[str, ...] = ()     # reasons for a ПРОВЕРИТЬ marker
    in_reserve: bool = False

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def spoken(self) -> bool:
        return self.kind in (BlockKind.STANDUP, BlockKind.VOICEOVER)


@dataclass(frozen=True)
class ScriptComment:
    id: str
    author: str
    text: str
    resolved: bool
    replies: tuple[str, ...]
    anchor_text: str | None
    block_ids: tuple[str, ...]
    links: tuple[str, ...]
    clocks: tuple[tuple[float, float | None], ...]
    ambiguous: bool = False

    @property
    def anchored(self) -> bool:
        return bool(self.block_ids)


@dataclass(frozen=True)
class AppendixSection:
    """A '# heading' section after the script, e.g. the transcript of a live."""

    title: str
    links: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class Script:
    title: str
    blocks: tuple[ScriptBlock, ...]
    reserve: tuple[ScriptBlock, ...] = ()
    appendix: tuple[AppendixSection, ...] = ()
    comments: tuple[ScriptComment, ...] = ()
    warnings: tuple[str, ...] = field(default=())

    def block(self, block_id: str) -> ScriptBlock:
        for b in self.blocks + self.reserve:
            if b.id == block_id:
                return b
        raise KeyError(block_id)

    def of_kind(self, kind: BlockKind) -> list[ScriptBlock]:
        return [b for b in self.blocks if b.kind == kind]

    @property
    def spoken_blocks(self) -> list[ScriptBlock]:
        return [b for b in self.blocks if b.spoken and b.lines]

    @property
    def open_comments(self) -> list[ScriptComment]:
        return [c for c in self.comments if not c.resolved]


# ---------- parsing ----------

MEDIA_KINDS = (BlockKind.LIVE, BlockKind.QUOTE, BlockKind.INSERT, BlockKind.BUTT)


def _strip_comment_marks(markdown: str) -> tuple[str, dict[str, tuple[int, int]]]:
    """Remove <comment_start/end id=..> marks; return clean text and id -> (start, end) offsets in it."""
    out: list[str] = []
    spans: dict[str, list[int]] = {}
    pos = 0
    length = 0
    for m in _COMMENT_MARK.finditer(markdown):
        chunk = markdown[pos:m.start()]
        out.append(chunk)
        length += len(chunk)
        spans.setdefault(m.group(2), [length, length])
        if m.group(1) == "end":
            spans[m.group(2)][1] = length
        pos = m.end()
    out.append(markdown[pos:])
    return "".join(out), {k: (v[0], v[1]) for k, v in spans.items()}


@dataclass
class _Line:
    raw: str
    visible: str
    start: int  # offset in clean markdown
    end: int


def _lines(clean: str) -> list[_Line]:
    result = []
    offset = 0
    for raw in clean.split("\n"):
        visible = strip_markdown(raw)
        if visible:
            result.append(_Line(raw, visible, offset, offset + len(raw)))
        offset += len(raw) + 1
    return result


def _is_bold_line(raw: str) -> bool:
    return raw.strip().startswith("**")


def _is_link_only(line: _Line) -> bool:
    return bool(find_urls(line.raw)) and not normalize(without_links(line.raw))


def _clock_of(line: _Line) -> Clock | None:
    """A line that starts with a timecode (the host never starts spoken text with one)."""
    text = without_links(line.raw)
    clocks = find_clocks(text)
    if not clocks or normalize(text[: clocks[0][0]]):
        return None
    first = clocks[0]
    second = clocks[1] if len(clocks) > 1 else None
    tail = lambda s: " ".join(s.split()).strip(" —–-.…")  # noqa: E731
    if second:
        return Clock(first[2], second[2], tail(text[first[1]:second[0]]), tail(text[second[1]:]))
    return Clock(first[2], None, tail(text[first[1]:]), "")


def _header(line: _Line, cues: CueVocabulary) -> tuple[BlockKind, str | None, str] | None:
    text = without_links(line.raw)
    m = _NUMBER_PREFIX.match(text)
    number = None
    if m and m.group(1) and not find_clocks(text[: m.end() + 1]):
        number = m.group(1)
        text = text[m.end():]
    found = cues.match(text)
    if not found:
        return None
    kind, cue = found
    label = text[len(cue):].split("http")[0].strip(" :.-—")
    return kind, number, label


def _is_word_line(visible: str, words: tuple[str, ...]) -> bool:
    return normalize(visible) in {normalize(w) for w in words}


@dataclass
class _Draft:
    kind: BlockKind
    header: str
    number: str | None
    label: str
    start: int
    end: int
    lines: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    raws: list[str] = field(default_factory=list)
    clocks: list[Clock] = field(default_factory=list)
    implicit: bool = False
    checks: list[str] = field(default_factory=list)

    def add(self, line: _Line, to: list[str] | None = None) -> None:
        if to is not None:
            to.append(line.visible)
        self.raws.append(line.raw)
        self.end = line.end


def _parse_blocks(lines: list[_Line], cues: CueVocabulary) -> tuple[list[_Draft], list[_Draft]]:
    main: list[_Draft] = []
    reserve: list[_Draft] = []
    target = main
    current: _Draft | None = None
    last_content: BlockKind | None = None  # kind of the last non-direction block

    def open_block(kind, line, header="", number=None, label="", implicit=False) -> _Draft:
        nonlocal last_content
        draft = _Draft(kind, header, number, label, line.start, line.end, implicit=implicit)
        draft.raws.append(line.raw)
        target.append(draft)
        if kind != BlockKind.DIRECTION:
            last_content = kind
        return draft

    for line in lines:
        if _is_word_line(line.visible, cues.end_words):
            target, current, last_content = reserve, None, None
            continue
        if target is reserve and _is_word_line(line.visible.rstrip(":"), cues.reserve_words):
            continue
        head = _header(line, cues)
        if head:
            kind, number, label = head
            current = open_block(kind, line, line.visible, number, label)
            continue
        if not normalize(line.visible):  # '…', '-': punctuation only, nothing to lose
            if current is not None:
                current.add(line)
            continue
        clock = _clock_of(line)
        in_media = current is not None and current.kind in MEDIA_KINDS
        in_direction = current is not None and current.kind == BlockKind.DIRECTION
        if _is_link_only(line) and current is not None and (in_media or in_direction):
            current.add(line)
            continue
        if clock is not None:
            if current is None or not (in_media or in_direction):
                current = open_block(BlockKind.DIRECTION, line, implicit=True)
                current.checks.append("timecode without a ЛАЙВ header")
            current.clocks.append(clock)
            current.add(line)
            continue
        if in_media and (_is_bold_line(line.raw) or current.kind == BlockKind.BUTT or find_urls(line.raw)):
            current.add(line, current.notes)
            continue
        if _is_bold_line(line.raw) or _is_link_only(line):
            current = open_block(BlockKind.DIRECTION, line)
            current.lines.append(line.visible)
            continue
        if current is None or in_direction:
            continuing = last_content in (BlockKind.STANDUP, BlockKind.VOICEOVER)
            kind = last_content if continuing else BlockKind.STANDUP
            current = open_block(kind, line, implicit=True)
            if not continuing:
                current.checks.append("text without a СТЕНДАП header")
        elif current.kind in (BlockKind.LIVE, BlockKind.INSERT) and not line.raw.lstrip().startswith("*"):
            # plain (not italic) text after a live is usually the host speaking again
            current = open_block(BlockKind.STANDUP, line, implicit=True)
            current.checks.append("text right after a live without a СТЕНДАП header")
        current.add(line, current.lines)
    return main, reserve


def _finish(drafts: list[_Draft], prefix: str, in_reserve: bool) -> list[tuple[ScriptBlock, int, int, str]]:
    blocks = []
    for i, d in enumerate(drafts, 1):
        links = tuple(dict.fromkeys(u for raw in d.raws for u in find_urls(raw)))
        checks = list(d.checks)
        if d.kind == BlockKind.LIVE and not links:
            checks.append("live without a link")
        if d.kind == BlockKind.LIVE and links and not d.clocks:
            checks.append("live without timecodes")
        if d.kind == BlockKind.DIRECTION and links and d.clocks:
            checks.append("direction with a link and timecodes: probably a live")
        block = ScriptBlock(
            id=f"{prefix}{i:03d}", kind=d.kind, header=d.header, number=d.number, label=d.label,
            lines=tuple(d.lines), notes=tuple(d.notes), links=links, clocks=tuple(d.clocks),
            implicit=d.implicit, checks=tuple(checks), in_reserve=in_reserve,
        )
        search = normalize(" ".join(strip_markdown(r) for r in d.raws))
        blocks.append((block, d.start, d.end, search))
    return blocks


def _split_sections(clean: str) -> tuple[str, int, list[tuple[str, str]]]:
    """(script text, its offset, [(title, body)]) — '# ' headings split the doc."""
    parts = re.split(r"(?m)^# (.+)$", clean)
    if len(parts) == 1:
        return clean, 0, []
    head, rest = parts[0], parts[1:]
    sections = [(rest[i].strip(), rest[i + 1]) for i in range(0, len(rest), 2)]
    if normalize(head):  # text before the first heading is the script itself
        return head, 0, sections
    first_title, first_body = sections[0]
    offset = clean.index(first_body, len(head))
    return first_body, offset, sections[1:]


def _search_index(blocks: list[tuple[ScriptBlock, int, int, str]]) -> tuple[str, list[tuple[int, int, str]]]:
    text_parts, spans, pos = [], [], 0
    for b, _, _, norm in blocks:
        if not norm:
            continue
        text_parts.append(norm)
        spans.append((pos, pos + len(norm), b.id))
        pos += len(norm) + 1
    return " ".join(text_parts), spans


def _find_anchor(anchor: str, haystack: str, spans: list[tuple[int, int, str]]) -> tuple[tuple[str, ...], bool]:
    needle = normalize(anchor)
    if len(needle) < 3:
        return (), False
    hits = [m.start() for m in re.finditer(re.escape(needle), haystack)]
    if hits:
        start = hits[0]
        end = start + len(needle)
        ids = tuple(bid for s, e, bid in spans if s < end and start < e)
        return ids, len(hits) > 1
    # fuzzy fallback: typos fixed in the doc after commenting, doubled spaces, etc.
    if len(needle) >= 12:
        res = fuzz.partial_ratio_alignment(needle, haystack, score_cutoff=90)
        if res is not None:
            ids = tuple(bid for s, e, bid in spans if s < res.dest_end and res.dest_start < e)
            return ids, False
    return (), False


def parse_script(doc: RawDoc, cues: CueVocabulary = DEFAULT_CUES) -> Script:
    clean, kix_spans = _strip_comment_marks(doc.markdown)
    script_text, script_offset, sections = _split_sections(clean)
    lines = _lines(script_text)
    for line in lines:
        line.start += script_offset
        line.end += script_offset
    main_drafts, reserve_drafts = _parse_blocks(lines, cues)
    if not main_drafts:
        raise ScriptError("no script blocks found — is this the right document?")
    main = _finish(main_drafts, "B", in_reserve=False)
    reserve = _finish(reserve_drafts, "R", in_reserve=True)
    positioned = main + reserve

    haystack, spans = _search_index(positioned)
    comments: list[ScriptComment] = []
    by_block: dict[str, list[str]] = {}
    highlights: dict[str, list[Highlight]] = {}
    warnings: list[str] = []
    for raw in doc.comments:
        ids: tuple[str, ...] = ()
        ambiguous = False
        if raw.anchor_id and raw.anchor_id in kix_spans:
            s, e = kix_spans[raw.anchor_id]
            ids = tuple(b.id for b, bs, be, _ in positioned if bs <= e and s <= be)
        if not ids and raw.anchor_text:
            ids, ambiguous = _find_anchor(raw.anchor_text, haystack, spans)
        clocks = tuple(
            (a[2], b[2] if b else None)
            for a, b in _pair_clocks(find_clocks(raw.text))
        )
        comment = ScriptComment(
            id=raw.id, author=raw.author, text=raw.text, resolved=raw.resolved, replies=raw.replies,
            anchor_text=raw.anchor_text, block_ids=ids, links=tuple(find_urls(raw.text)),
            clocks=clocks, ambiguous=ambiguous,
        )
        comments.append(comment)
        for bid in ids:
            by_block.setdefault(bid, []).append(raw.id)
            if raw.anchor_text:
                highlights.setdefault(bid, []).append(Highlight(raw.id, strip_markdown(raw.anchor_text)))
        if not raw.resolved and raw.anchor_text and not ids:
            warnings.append(f"comment {raw.id} ({raw.author}): anchor not found in the script")

    def attach(block: ScriptBlock) -> ScriptBlock:
        checks = list(block.checks)
        if any(c.ambiguous for c in comments if block.id in c.block_ids):
            checks.append("comment anchor text occurs more than once")
        return replace(
            block,
            comment_ids=tuple(by_block.get(block.id, ())),
            highlights=tuple(highlights.get(block.id, ())),
            checks=tuple(checks),
        )

    appendix = tuple(
        AppendixSection(title=title, links=tuple(find_urls(body)), text=strip_markdown(body))
        for title, body in sections
    )
    return Script(
        title=doc.title,
        blocks=tuple(attach(b) for b, _, _, _ in main),
        reserve=tuple(attach(b) for b, _, _, _ in reserve),
        appendix=appendix,
        comments=tuple(comments),
        warnings=tuple(warnings),
    )


def _pair_clocks(clocks: list[tuple[int, int, float]]):
    """'1:31-1:38' -> one range; lone timecodes -> (tc, None)."""
    out = []
    i = 0
    while i < len(clocks):
        if i + 1 < len(clocks) and clocks[i + 1][0] - clocks[i][1] <= 3:
            out.append((clocks[i], clocks[i + 1]))
            i += 2
        else:
            out.append((clocks[i], None))
            i += 1
    return out


# ---------- part 1 / part 2 ----------

def _locate(words_text: str, blocks: tuple[ScriptBlock, ...], from_end: bool) -> tuple[int, int]:
    """(block index, line index) where the phrase occurs in a spoken block."""
    needle = normalize(words_text)
    if not needle:
        raise ScriptError("empty boundary phrase")
    order = range(len(blocks) - 1, -1, -1) if from_end else range(len(blocks))
    best: tuple[float, int, int] | None = None
    for bi in order:
        block = blocks[bi]
        if not block.spoken:
            continue
        for li, line in enumerate(block.lines):
            hay = normalize(line)
            if needle in hay:
                return bi, li
            score = fuzz.partial_ratio(needle, hay) if len(needle) >= 12 else 0
            if score >= 90 and (best is None or score > best[0]):
                best = (score, bi, li)
    if best:
        return best[1], best[2]
    raise ScriptError(f"phrase not found in the script: {words_text!r}")


def select_part(script: Script, first_words: str | None = None, last_words: str | None = None) -> Script:
    """Keep only the part between the line containing first_words and the line containing last_words."""
    blocks = script.blocks
    start_b, start_l = _locate(first_words, blocks, from_end=False) if first_words else (0, 0)
    end_b, end_l = _locate(last_words, blocks, from_end=True) if last_words else (len(blocks) - 1, None)
    if (end_b, end_l if end_l is not None else 10**9) < (start_b, start_l):
        raise ScriptError("the last-words phrase comes before the first-words phrase")
    kept = list(blocks[start_b:end_b + 1])
    first = kept[0]
    if first.spoken:
        kept[0] = replace(first, lines=first.lines[start_l:])
    if end_l is not None:
        last_i = len(kept) - 1
        last = kept[last_i]
        cut_from = start_l if last_i == 0 and first.spoken else 0
        kept[last_i] = replace(last, lines=last.lines[: end_l + 1 - cut_from])
    ids = {b.id for b in kept}
    return replace(
        script,
        blocks=tuple(kept),
        reserve=(),
        comments=tuple(c for c in script.comments if set(c.block_ids) & ids),
    )
