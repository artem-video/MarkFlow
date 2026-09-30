import importlib

import pytest

PACKAGES = [
    "markflow",
    "markflow.shared",
    "markflow.domain",
    "markflow.application",
    "markflow.infra",
    "markflow.infra.asr",
    "markflow.infra.media",
    "markflow.infra.google",
    "markflow.infra.downloader",
    "markflow.infra.prproj",
    "markflow.infra.bridge",
    "markflow.infra.llm",
    "markflow.infra.assets",
    "markflow.profiles",
    "acceptance",
    "tools",
]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_imports(name):
    assert importlib.import_module(name) is not None


def test_version_is_set():
    import markflow

    assert markflow.__version__
