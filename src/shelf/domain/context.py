"""The whole picture: what already binds a repository, so that no agent writes something that contradicts it."""

from collections.abc import Mapping, Sequence

CATEGORIES: dict[str, tuple[str, ...]] = {
    "Conventions and agent instructions": (
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        "CONTRIBUTING.md",
        "README.md",
        ".github/copilot-instructions.md",
    ),
    "Existing specifications (the contract: do not contradict them)": (
        "openspec/specs/*/spec.md",
        "specs/**/*.md",
        "docs/specs/**/*.md",
    ),
    "Architecture decisions (do not contradict them without saying so)": (
        "docs/adr/[0-9]*.md",
        "docs/decisions/[0-9]*.md",
        "adr/[0-9]*.md",
    ),
    "How the repository's CI judges a change (what must be green)": (
        ".github/workflows/*.yml",
        ".github/workflows/*.yaml",
    ),
    "Architecture and engineering notes": ("ARCHITECTURE.md", "docs/ENGINEERING.md", "docs/architecture*.md"),
}
"""For each kind of document, where repositories usually keep it (glob patterns)."""

EARLIER_WORK = "docs/shelf/*/spec.md"
"""The specs of earlier pieces of work done here: they describe behaviour that already exists."""

LIMIT = 25
"""How many paths of one kind are listed."""


def context_brief(found: Mapping[str, Sequence[str]], earlier: Sequence[str]) -> str:
    """The paragraph that points an agent at everything that already binds the repository.

    ``found`` maps a category to the paths that exist; ``earlier`` lists the specs of earlier work. Empty when the
    repository has none of it.
    """
    lines: list[str] = []
    for title, paths in found.items():
        if paths:
            lines += [f"{title}:", *(f"- {path}" for path in paths[:LIMIT]), ""]
    if earlier:
        lines += [
            "Specs of earlier work done here (behaviour that already exists):",
            *(f"- {p}" for p in earlier[:LIMIT]),
            "",
        ]
    if not lines:
        return ""
    intro = (
        "The whole picture. Before you decide anything, read what already binds this repository. "
        "Your work must not contradict it. If it has to, say so explicitly, name the file and the requirement, and why."
    )
    return "\n".join([intro, "", *lines]).rstrip()
