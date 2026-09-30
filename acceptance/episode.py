"""Episode config for the acceptance gates (acceptance/episodes/*.yaml)."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def expand(path: str) -> Path:
    text = os.path.expandvars(os.path.expanduser(path))
    if os.name != "nt" and "%USERPROFILE%" in text:
        text = text.replace("%USERPROFILE%", str(Path.home()))
    text = text.replace("\\", os.sep) if os.name != "nt" else text
    p = Path(text)
    return p if p.is_absolute() else REPO / p


@dataclass(frozen=True)
class Episode:
    name: str
    profile: str
    doc_id: str | None
    export: Path | None
    anchored: Path | None
    first_words: str | None
    last_words: str | None
    sources: tuple[Path, ...]
    base_project: Path
    sequence: str
    cache: Path
    asr_engines: tuple[str, ...]

    @staticmethod
    def load(path: Path) -> "Episode":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        script = data.get("script", {})
        return Episode(
            name=data["episode"], profile=data["profile"], doc_id=script.get("doc_id"),
            export=expand(script["export"]) if script.get("export") else None,
            anchored=expand(script["anchored"]) if script.get("anchored") else None,
            first_words=script.get("first_words"), last_words=script.get("last_words"),
            sources=_sources(data["sources"]), base_project=expand(data["base_project"]),
            sequence=data["sequence"], cache=expand(data["cache"]),
            asr_engines=tuple(data.get("asr_engines", ["gigaam-v3", "parakeet-v3"])),
        )


def _sources(entries: list[str]) -> tuple[Path, ...]:
    """Paths or glob patterns ('**' allowed); one file per name, missing plain paths kept (reported later)."""
    out: dict[str, Path] = {}
    for entry in entries:
        path = expand(entry)
        if any(ch in str(path) for ch in "*?["):
            anchor = Path(path.anchor)
            matches = sorted(anchor.glob(str(path.relative_to(anchor)))) if path.is_absolute() else []
            for m in matches:
                if m.is_file():
                    out.setdefault(m.name.lower(), m)
        else:
            out.setdefault(path.name.lower(), path)
    return tuple(out.values())


def branch_name() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO, capture_output=True, text=True)
        name = out.stdout.strip() or "unknown"
    except OSError:
        name = "unknown"
    return name.replace("/", "-")


def report_dir() -> Path:
    d = REPO / "acceptance" / "reports" / branch_name()
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_output_path(base: Path, stage: str = "MF1_draft") -> Path:
    """<base>_MF1_draft.prproj next to the base; never an existing file."""
    out = base.with_name(f"{base.stem}_{stage}.prproj")
    n = 2
    while out.exists():
        out = base.with_name(f"{base.stem}_{stage}_{n}.prproj")
        n += 1
    return out
