"""Derived data cache (transcripts, envelopes, audio) keyed by a fast fingerprint of the source.

Sources can be 45 GB (Keyed-Video ProRes), so the fingerprint reads size + three 4 MB windows
(head, middle, tail) instead of the whole file. A re-exported or edited file changes it.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

WINDOW = 4 * 1024 * 1024


def fast_fingerprint(path: Path, window: int = WINDOW) -> str:
    path = Path(path)
    size = path.stat().st_size
    h = hashlib.sha256(f"{size}:".encode())
    with path.open("rb") as f:
        for offset in sorted({0, max(0, size // 2 - window // 2), max(0, size - window)}):
            f.seek(offset)
            h.update(f.read(window))
    return h.hexdigest()[:32]


class JsonFileStore:
    """key 'transcript/gigaam-v3/<fp>' -> <root>/transcript/gigaam-v3/<fp>.json"""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        parts = key.split("/")
        if any(p in ("", ".", "..") for p in parts):
            raise ValueError(f"bad cache key: {key!r}")
        return self.root.joinpath(*parts).with_suffix(".json")

    def get(self, key: str) -> dict | None:
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None  # a half-written file from a crash: recompute

    def put(self, key: str, value: dict) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)
