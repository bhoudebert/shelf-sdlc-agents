"""Loading a role's system prompt from the package."""

from functools import cache
from importlib import resources


@cache
def load_prompt(role: str) -> str:
    """The system prompt of ``role``; raises ``FileNotFoundError`` for a role that has none."""
    return resources.files("shelf.prompts").joinpath(f"{role}.md").read_text(encoding="utf-8")
