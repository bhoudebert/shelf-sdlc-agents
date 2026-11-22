from shelf.domain.brief import DISPUTE_MARK, brief_of

ARBITRATED = (
    "Question: Should the limit be 10 or 50?\n- 10: safer, may reject real use\n- 50: matches the request\n"
    "Recommended answer: Use 50 and say so under Assumptions.\n"
)


def test_a_dispute_nobody_arbitrated_is_asked_as_a_question_with_its_first_lines() -> None:
    detail = "the reviewer and the author disagree, 2 point(s) came back:\n1. ADR line 17\n2. spec R3\n3. x\n4. y\n5. z"
    brief = brief_of(detail)
    assert brief.question == "The reviewer and the author cannot agree: 2 point(s) came back. What should happen?"
    assert not brief.arbitrated
    assert brief.short.splitlines() == detail.splitlines()[:4]
    assert brief.dispute == detail
    assert brief.recommended == ""


def test_a_review_that_used_its_rounds_says_so() -> None:
    assert "used its 3 rounds" in brief_of("limit of 3 rounds reached:\nstill vague").question


def test_a_review_that_could_not_decide_says_so() -> None:
    assert brief_of("the limit is not defined").question == "The reviewer could not decide. What should happen?"


def test_an_arbitrators_brief_gives_the_question_and_the_answer_to_send() -> None:
    brief = brief_of(f"{ARBITRATED}{DISPUTE_MARK}1. the limit is not defined")
    assert brief.arbitrated
    assert brief.question == "Should the limit be 10 or 50?"
    assert brief.recommended == "Use 50 and say so under Assumptions."
    assert brief.brief.startswith("Question:")
    assert brief.dispute == "1. the limit is not defined"
    assert brief.short == "1. the limit is not defined"


def test_an_arbitrator_that_gave_no_question_line_is_read_by_its_first_line() -> None:
    brief = brief_of(f"A person must pick a limit.\nOptions follow.{DISPUTE_MARK}the dispute")
    assert brief.question == "A person must pick a limit."
    assert brief.recommended == ""


def test_what_is_shown_first_is_short() -> None:
    brief = brief_of("x" * 3000)
    assert len(brief.short) <= 501
    assert brief.short.endswith("…")
    assert len(brief.dispute) == 3000
