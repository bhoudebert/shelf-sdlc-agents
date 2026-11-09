import os

import pytest

HOOK_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX", "GIT_OBJECT_DIRECTORY")
"""What git exports to a hook: tests that run git in a temporary directory must not inherit them."""


@pytest.fixture(autouse=True)
def _git_without_hook_environment(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    for name in HOOK_VARIABLES:
        if name in os.environ:
            monkeypatch.delenv(name)
