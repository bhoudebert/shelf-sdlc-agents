"""Where the lasting results of a run go in the repository, and what each agent is told about them."""

from dataclasses import dataclass
from enum import StrEnum

from shelf.domain.pipeline import Phase


class Conflicts(StrEnum):
    """What a contradiction between a new decision record and an earlier one does."""

    BLOCK = "block"
    WARN = "warn"
    OFF = "off"


SPEC = "spec"
ADR = "adr"
KINDS = frozenset({SPEC, ADR})
"""The results a run can write into the repository besides its own documents."""


@dataclass(frozen=True, slots=True)
class Results:
    """The ``[results]`` section of ``.shelf/config.toml``."""

    specs: str = "openspec/specs"
    decisions: str = "docs/adr"
    write: frozenset[str] = KINDS
    conflicts: Conflicts = Conflicts.BLOCK


def _specs(results: Results) -> str:
    return (
        f"The spec has been approved: write its requirements into the repository's own specs, `{results.specs}/`, in "
        "the same terms as `spec.md`. One folder per capability with a `spec.md` of requirements, each with scenarios "
        "(WHEN / THEN). Change the requirement that already exists when behaviour changes, add one when it is new, and "
        f"follow the format of the specs you find there. If `{results.specs}/` does not exist, create it in the form "
        "the repository's conventions describe (`AGENTS.md`, `CONTRIBUTING.md`), or in the standard form, with a "
        "`README.md` that says how to write a requirement. Do not skip it because the folder is missing."
    )


def _records(results: Results) -> str:
    return (
        f"If the change makes a lasting architectural decision, write its record in `{results.decisions}/`, numbered "
        "after the last one and following the repository's template (its status is `proposed`). A decision is lasting "
        "when it would be expensive to reverse or when a newcomer would ask why. If it replaces an earlier decision, "
        "write `Supersedes: NNNN` in the new record and change only the status line of the earlier one to "
        f"`superseded by NNNN`; never rewrite an accepted record. If `{results.decisions}/` does not exist, create it: "
        "a `README.md`, the template, and a first record that decides to keep records, then yours."
    )


def _design_review(results: Results) -> str:
    compare = (
        f"Read every earlier accepted record in `{results.decisions}/` and compare the new record, and the "
        "design, with them. A contradiction is acceptable only when the request says to change that decision, or the "
        "new record says `Supersedes: NNNN` for it."
    )
    match results.conflicts:
        case Conflicts.BLOCK:
            return f"{compare} Any other contradiction is a major issue: name both records. Do not approve it."
        case Conflicts.WARN:
            return (
                f"{compare} Report any other contradiction naming both records, "
                "but do not ask for changes because of it."
            )
        case Conflicts.OFF:
            return ""


def _code_review(results: Results) -> str:
    return (
        f"When the work changes behaviour, the requirement must be changed in `{results.specs}/`; when it makes a "
        f"lasting decision, its record must be in `{results.decisions}/`. A missing one is an issue."
    )


def results_note(results: Results, phase: Phase) -> str:
    """What the agent of ``phase`` is told about specs and decision records; empty when it has nothing to do there."""
    spec, adr = SPEC in results.write, ADR in results.write
    match phase:
        case Phase.DESIGN if spec or adr:
            return "\n\n".join(
                part for part in (_specs(results) if spec else "", _records(results) if adr else "") if part
            )
        case Phase.DESIGN_REVIEW if adr:
            return _design_review(results)
        case Phase.CODE_REVIEW if spec or adr:
            return _code_review(results)
        case _:
            return ""
