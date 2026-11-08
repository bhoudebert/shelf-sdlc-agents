import pytest

from shelf.domain.commands import is_ours, parse_command
from shelf.domain.work import DecisionKind


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("/shelf approve", (DecisionKind.APPROVE, "")),
        ("/shelf APPROVE", (DecisionKind.APPROVE, "")),
        ("/shelf changes rename the endpoint", (DecisionKind.CHANGES, "rename the endpoint")),
        ("/shelf changes first line\nsecond line", (DecisionKind.CHANGES, "first line\nsecond line")),
        ("  /shelf abort  ", (DecisionKind.ABORT, "")),
        ("/shelf resume try again", (DecisionKind.RESUME, "try again")),
    ],
)
def test_a_known_command_is_read_with_its_note(body: str, expected: tuple[DecisionKind, str]) -> None:
    assert parse_command(body) == expected


@pytest.mark.parametrize("body", ["", "approve", "/shelf", "/shelf deploy", "please /shelf approve", "/adf approve"])
def test_anything_else_is_not_a_command(body: str) -> None:
    assert parse_command(body) is None


def test_the_factorys_own_comments_are_recognised() -> None:
    assert is_ours("<!-- shelf:work-1 -->\nhello")
    assert not is_ours("/shelf approve")
