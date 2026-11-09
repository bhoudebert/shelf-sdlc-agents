import pytest

from shelf.domain.model import RepoRef
from shelf.domain.reference import File, Imported, Thread, combine, parse_reference
from shelf.domain.result import Err, Ok

REPO = RepoRef("acme", "shop")


@pytest.mark.parametrize(
    "text", ["#42", "42", " #42 ", "https://github.com/acme/shop/issues/42", "https://github.com/acme/shop/pull/42/"]
)
def test_an_issue_or_pull_request_of_this_repository_is_a_thread(text: str) -> None:
    assert parse_reference(text, REPO) == Ok(Thread(42))


def test_a_comment_anchor_on_the_address_is_ignored() -> None:
    assert parse_reference("https://github.com/acme/shop/issues/42#issuecomment-9", REPO) == Ok(Thread(42))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("docs/specs/loyalty.md", File("docs/specs/loyalty.md")),
        ("README.md", File("README.md")),
        ("https://github.com/acme/shop/blob/main/docs/a.md", File("docs/a.md", "main")),
        ("https://github.com/ACME/shop/blob/v1/docs/a.md#L10", File("docs/a.md", "v1")),
    ],
)
def test_a_path_or_a_file_address_of_this_repository_is_a_file(text: str, expected: File) -> None:
    assert parse_reference(text, REPO) == Ok(expected)


@pytest.mark.parametrize(
    "text",
    [
        "../secrets.md",
        "docs/../../etc/passwd",
        "/etc/passwd",
        "docs\\a.md",
        "https://evil.example/acme/shop/issues/1",
        "https://github.com/other/repo/issues/1",
        "https://github.com/other/repo/blob/main/a.md",
        "x/" * 150,
    ],
)
def test_anything_that_leaves_this_repository_or_climbs_out_of_it_is_refused(text: str) -> None:
    assert isinstance(parse_reference(text, REPO), Err)


def test_the_message_for_another_repository_names_both() -> None:
    result = parse_reference("https://github.com/other/repo/issues/1", REPO)
    assert result == Err("that address belongs to other/repo, not to acme/shop")


def test_imported_text_says_where_it_came_from_and_keeps_what_the_requester_added() -> None:
    text = combine(Imported("docs/spec.md", "The spec.\n"), "Also handle empty carts.")
    assert text.startswith("> Imported from docs/spec.md\n\nThe spec.")
    assert "Note from the requester:\n\nAlso handle empty carts." in text


def test_imported_text_alone_has_no_note() -> None:
    assert "Note from the requester" not in combine(Imported("#42", "# Title\n\nbody"), "  ")
