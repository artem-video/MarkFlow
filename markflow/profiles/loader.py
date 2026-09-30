"""Load profiles/<channel>/profile.yaml into a checked Profile."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from markflow.domain.profile import Profile

PROFILES_DIR = Path(__file__).resolve().parents[2] / "profiles"


class ProfileError(ValueError):
    pass


def profile_path(channel: str, root: Path = PROFILES_DIR) -> Path:
    return Path(root) / channel / "profile.yaml"


def load_profile(channel: str, root: Path = PROFILES_DIR) -> Profile:
    path = profile_path(channel, root)
    if not path.is_file():
        raise ProfileError(f"no profile for channel {channel!r}: {path} not found")
    return parse_profile(path.read_text(encoding="utf-8"), source=str(path))


def parse_profile(text: str, source: str = "<profile>") -> Profile:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ProfileError(f"{source}: not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"{source}: expected a mapping at the top level")
    try:
        return Profile.model_validate(data)
    except ValidationError as exc:
        raise ProfileError(f"{source}: {exc}") from exc


def list_profiles(root: Path = PROFILES_DIR) -> list[str]:
    return sorted(p.parent.name for p in Path(root).glob("*/profile.yaml"))
