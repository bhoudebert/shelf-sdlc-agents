import pytest

from shelf.domain.titles import MAX_TITLE, SUMMARY_LENGTH, clean_title, fallback_title, summary


def test_the_last_line_of_the_answer_is_the_title() -> None:
    assert (
        clean_title("I read the git log.\n\nfeat(api): accept a time zone\n", "fallback")
        == "feat(api): accept a time zone"
    )


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("`fix: x`", "fix: x"),
        ('"fix: x"', "fix: x"),
        ("Title: fix: x", "fix: x"),
        ("PR title: **fix: x**", "fix: x"),
        ("fix:   many    spaces", "fix: many spaces"),
    ],
)
def test_decoration_is_removed_from_a_title(answer: str, expected: str) -> None:
    assert clean_title(answer, "fallback") == expected


@pytest.mark.parametrize("answer", ["", "   \n  ", "x" * (MAX_TITLE + 1)])
def test_nothing_usable_falls_back(answer: str) -> None:
    assert clean_title(answer, "fallback") == "fallback"


def test_the_fallback_is_the_first_line_of_the_request_cut_to_fit() -> None:
    assert fallback_title("\n\n  Add badges  \nmore") == "Add badges"
    assert len(fallback_title("x" * 200)) == 70
    assert fallback_title("  ") == "shelf work"


def test_the_board_summary_is_the_first_line_of_the_request_without_markdown_headings() -> None:
    assert summary("\n# Loyalty points\nmore detail") == "Loyalty points"
    assert summary("") == ""


def test_a_long_first_line_is_shortened_with_an_ellipsis() -> None:
    shown = summary("word " * 40)
    assert len(shown) == SUMMARY_LENGTH
    assert shown.endswith("…")
