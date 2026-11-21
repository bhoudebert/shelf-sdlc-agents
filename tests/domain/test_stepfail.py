import pytest

from shelf.domain.stepfail import explain_model_failure, unresolvable

ORIGINAL = "API Error: Can't reach the API server — check your internet or DNS (EAI_AGAIN)"


def test_an_error_that_says_the_model_was_not_reached_keeps_its_text_and_adds_what_to_check() -> None:
    explained = explain_model_failure(ORIGINAL)

    assert explained.startswith(ORIGINAL)
    assert "SHELF_STEP_DNS" in explained
    assert "resolve" in explained


@pytest.mark.parametrize(
    "text",
    [
        "getaddrinfo EAI_AGAIN api.anthropic.com",
        "connect ECONNREFUSED 127.0.0.11:53",
        "request to x failed: ENOTFOUND api.anthropic.com",
    ],
)
def test_the_usual_ways_of_not_reaching_the_model_are_recognised(text: str) -> None:
    assert "SHELF_STEP_DNS" in explain_model_failure(text)


@pytest.mark.parametrize("text", ["", "max turns reached", "the tests failed", "API Error: 529 overloaded"])
def test_any_other_failure_is_left_as_it_is(text: str) -> None:
    assert explain_model_failure(text) == text


def test_the_advice_is_added_once() -> None:
    once = explain_model_failure(ORIGINAL)

    assert explain_model_failure(once) == once


def test_the_message_for_a_name_that_does_not_resolve_names_the_host() -> None:
    message = unresolvable("api.anthropic.com", "Temporary failure in name resolution")

    assert "api.anthropic.com" in message
    assert "Temporary failure in name resolution" in message
    assert "SHELF_STEP_DNS" in message
