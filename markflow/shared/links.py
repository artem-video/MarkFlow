"""Pure helpers for links of lives (no network, no urllib)."""

from __future__ import annotations

import re

_URL = re.compile(r"^(?:[a-z]+://)?(?P<host>[^/?#]+)(?P<path>/[^?#]*)?(?:\?(?P<query>[^#]*))?(?:#(?P<frag>.*))?$", re.I)


def live_key(url: str) -> str:
    """The same video behind different links (youtu.be / youtube.com, ?t=, ?si=, shorts) has one key."""
    m = _URL.match(url.strip().lstrip("﻿"))
    if not m:
        return url.strip()
    host = m.group("host").lower().removeprefix("www.")
    path = m.group("path") or ""
    if host == "youtu.be":
        return "youtube:" + path.strip("/")
    if host.endswith("youtube.com"):
        if path.startswith("/shorts/"):
            return "youtube:" + path.split("/")[2]
        v = re.search(r"(?:^|&)v=([^&]+)", m.group("query") or "")
        if v:
            return "youtube:" + v.group(1)
    return host + path.rstrip("/") + (("#" + m.group("frag")) if m.group("frag") else "")
