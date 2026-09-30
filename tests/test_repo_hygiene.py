"""Hard rules 4 and 5: no secrets and no big media in git."""

import fnmatch
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 5 * 1024 * 1024

SECRET_PATTERNS = [
    "gemini_api.txt", "*.api.txt", ".env", ".env.*", "*credentials*.json",
    "service_account*.json", "client_secret*.json", "token*.json",
]
SECRET_ALLOWED = {".env.example"}

MEDIA_PATTERNS = ["*.mov", "*.mp4", "*.mxf", "*.mkv", "*.avi", "*.wav", "*.mp3", "*.prproj", "*.prlock"]


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
        ).stdout.decode("utf-8")
        return [ROOT / p for p in out.split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        skip = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}
        return [p for p in ROOT.rglob("*") if p.is_file() and not skip & set(p.parts)]


def test_no_file_over_5mb():
    big = [str(p.relative_to(ROOT)) for p in tracked_files() if p.exists() and p.stat().st_size > MAX_BYTES]
    assert big == []


def test_no_secrets_tracked():
    leaked = [
        str(p.relative_to(ROOT))
        for p in tracked_files()
        if p.name not in SECRET_ALLOWED and any(fnmatch.fnmatch(p.name, pat) for pat in SECRET_PATTERNS)
    ]
    assert leaked == []


def test_media_only_in_fixtures():
    fixtures = ROOT / "tests" / "fixtures"
    templates = ROOT / "templates"  # small empty base projects saved by Premiere (PLAN 0.3), not media
    stray = [
        str(p.relative_to(ROOT))
        for p in tracked_files()
        if any(fnmatch.fnmatch(p.name.lower(), pat) for pat in MEDIA_PATTERNS)
        and fixtures not in p.parents
        and not (templates in p.parents and p.suffix.lower() == ".prproj")
    ]
    assert stray == []
