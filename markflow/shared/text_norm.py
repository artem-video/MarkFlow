"""Text normalisation for matching script <-> transcript <-> comment anchors. Pure."""

from __future__ import annotations

import re
import unicodedata

_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_MD_AUTOLINK = re.compile(r"<(https?://[^>\s]+)>")
_MD_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")
_URL = re.compile(r"https?://[^\s<>()\]\[\"'«»]+", re.IGNORECASE)
_HOST = re.compile(r"https?://[\w-]+(\.[\w-]+)+", re.IGNORECASE)  # a real host, not a torn 'https://www.'
_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACES = re.compile(r"\s+")


def strip_markdown(text: str) -> str:
    """Remove Google-Docs-markdown decoration, keep the visible text."""
    text = _MD_LINK.sub(lambda m: m.group(1), text)
    text = _MD_AUTOLINK.sub(lambda m: m.group(1), text)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?<!\w)\*(?!\s)|(?<!\s)\*(?!\w)", "", text)
    text = _MD_ESCAPE.sub(r"\1", text)
    text = text.replace("\xa0", " ")
    return _SPACES.sub(" ", text).strip()


def unescape_markdown(text: str) -> str:
    return _MD_ESCAPE.sub(r"\1", text)


def find_urls(text: str) -> list[str]:
    """URLs in raw markdown, de-duplicated in order of appearance, markdown escapes removed.

    Link targets win over link text: Docs often shows a broken text ('https://www. youtube.com/…')
    over a correct target.
    """
    seen: list[str] = []
    candidates = [m.group(2) for m in _MD_LINK.finditer(text)]
    rest = _MD_LINK.sub(" ", text)
    candidates += _URL.findall(unescape_markdown(rest))
    for raw in candidates:
        url = unescape_markdown(raw).strip().rstrip(".,;:!?*")
        if _URL.fullmatch(url) and _HOST.match(url) and url not in seen:
            seen.append(url)
    return seen


def without_links(text: str) -> str:
    """Visible text with every link (markdown, autolink, bare URL, broken 'https://www. ') removed."""
    text = _MD_LINK.sub(" ", text)
    text = _MD_AUTOLINK.sub(" ", text)
    text = _URL.sub(" ", unescape_markdown(text))
    return strip_markdown(text)


def normalize(text: str) -> str:
    """Lower case, ё->е, no punctuation, single spaces. For matching only, never for display."""
    text = unicodedata.normalize("NFKC", strip_markdown(text)).lower().replace("ё", "е")
    text = _NON_WORD.sub(" ", text).replace("_", " ")
    return _SPACES.sub(" ", text).strip()


def words(text: str) -> list[str]:
    return normalize(text).split()
