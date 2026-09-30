"""Interfaces the application layer needs from infra. Concrete classes live in markflow/infra."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np

from markflow.domain.transcript import Word


class Audio(Protocol):
    def extract(self, source: Path, fingerprint: str) -> Path:
        """16 kHz mono WAV of the source's audio (cached, the source is never touched)."""

    def read(self, wav: Path) -> tuple[np.ndarray, int]:
        """(mono float samples, sample rate)."""

    def extract_window(self, source: Path, start: float, duration: float, key: str) -> Path:
        """16 kHz mono WAV of [start, start + duration) of the source (cached under `key`)."""


class AsrEngine(Protocol):
    name: str

    def transcribe(self, wav: Path) -> list[Word]: ...

    def close(self) -> None:
        """Free the GPU: only one model in memory at a time (RTX 4060 8 GB)."""


class AsrEngineFactory(Protocol):
    name: str

    def load(self) -> AsrEngine: ...


class JsonStore(Protocol):
    def get(self, key: str) -> dict | None: ...

    def put(self, key: str, value: dict) -> None: ...


class Fingerprinter(Protocol):
    def __call__(self, path: Path) -> str: ...
