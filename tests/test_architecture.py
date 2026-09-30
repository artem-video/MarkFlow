"""Layer rules from CLAUDE.md, checked on every push.

domain  -> may use only domain + shared, no I/O
shared  -> may use only shared, no I/O
application -> must not import concrete infra
infra   -> must not import application
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "markflow"

# Standard-library modules that mean "touches the outside world".
IO_MODULES = {
    "subprocess", "socket", "shutil", "urllib", "http", "requests",
    "ftplib", "smtplib", "sqlite3", "tempfile", "glob", "gzip", "zipfile",
}

RULES = {
    "shared": {"forbid_pkgs": {"domain", "application", "infra", "profiles"}, "no_io": True},
    "domain": {"forbid_pkgs": {"application", "infra", "profiles"}, "no_io": True},
    "application": {"forbid_pkgs": {"infra"}, "no_io": False},
    "infra": {"forbid_pkgs": {"application"}, "no_io": False},
}


def _imported_modules(tree: ast.AST) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.lineno, node.module))
    return found


def check_source(layer: str, source: str, filename: str = "<src>") -> list[str]:
    """Return human-readable violations for one module of the given layer."""
    rule = RULES[layer]
    tree = ast.parse(source, filename=filename)
    problems = []
    for lineno, mod in _imported_modules(tree):
        parts = mod.split(".")
        if parts[0] == "markflow" and len(parts) > 1 and parts[1] in rule["forbid_pkgs"]:
            problems.append(f"{filename}:{lineno} {layer} imports {mod}")
        if rule["no_io"] and parts[0] in IO_MODULES:
            problems.append(f"{filename}:{lineno} {layer} imports I/O module {mod}")
    if rule["no_io"]:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                problems.append(f"{filename}:{node.lineno} {layer} calls open()")
    return problems


def _layer_files():
    for layer in RULES:
        for path in sorted((PKG / layer).rglob("*.py")):
            if not path.name.startswith("test_"):
                yield layer, path


@pytest.mark.parametrize("layer,path", list(_layer_files()), ids=lambda v: str(v))
def test_layer_rules(layer, path):
    source = path.read_text(encoding="utf-8")
    assert check_source(layer, source, str(path.relative_to(ROOT))) == []


# The guard itself must work, otherwise an empty repo would pass trivially.

@pytest.mark.parametrize(
    "layer,source",
    [
        ("domain", "from markflow.infra.media import ffmpeg"),
        ("domain", "import markflow.application.build_draft"),
        ("domain", "import subprocess"),
        ("domain", "data = open('x.txt').read()"),
        ("shared", "from markflow.domain import edit_plan"),
        ("application", "from markflow.infra.prproj.writer import write"),
        ("infra", "from markflow.application import build_draft"),
    ],
)
def test_guard_catches_violation(layer, source):
    assert check_source(layer, source) != []


@pytest.mark.parametrize(
    "layer,source",
    [
        ("domain", "from markflow.shared import timecode\nimport pydantic"),
        ("application", "from markflow.domain import edit_plan"),
        ("infra", "import subprocess\nfrom markflow.domain import edit_plan"),
    ],
)
def test_guard_allows_legal_imports(layer, source):
    assert check_source(layer, source) == []
