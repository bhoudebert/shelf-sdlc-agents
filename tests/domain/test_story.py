from shelf.domain.pipeline import Phase
from shelf.domain.story import SPEAKERS, Posted, Voice, agent_comment, classify, person_comment, superseded


def test_an_agent_speaks_under_its_role_title_with_a_marker() -> None:
    text = agent_comment("work-1", "spec_critic", "Too vague.")
    assert text.startswith("<!-- shelf-agent:spec_critic:work-1 -->\n**Spec reviewer** · agent\n\nToo vague.")


def test_an_agent_comment_is_read_back_as_that_agent() -> None:
    message = classify(agent_comment("work-1", "architect", "Use a new module."), "shelf-sdlc[bot]")
    assert (message.voice, message.speaker, message.body) == (Voice.AGENT, "Architect", "Use a new module.")


def test_a_person_speaking_through_the_interface_is_read_back_as_that_person() -> None:
    message = classify(person_comment("work-1", "alice", "Please add limits."), "shelf-sdlc[bot]")
    assert (message.voice, message.speaker, message.body) == (Voice.PERSON, "alice", "Please add limits.")


def test_a_person_commenting_on_github_is_a_person() -> None:
    message = classify("Looks fine to me.", "bob")
    assert (message.voice, message.speaker) == (Voice.PERSON, "bob")


def test_other_bots_are_not_mistaken_for_people_or_agents() -> None:
    assert classify("Build passed", "ci[bot]").voice is Voice.OTHER


def test_the_progress_summary_is_recognised() -> None:
    assert (
        classify("<!-- shelf-progress:work-1 -->\n### shelf-sdlc: progress", "shelf-sdlc[bot]").voice is Voice.SUMMARY
    )


def test_every_agent_role_has_a_person_to_stand_in_for() -> None:
    for role in ("intake", "spec_critic", "architect", "design_reviewer", "planner", "implementer", "code_reviewer"):
        assert role in SPEAKERS


def posted(body: str, *, hidden: bool = False, node: str | None = None) -> Posted:
    return Posted(node or body[:12], body, hidden)


def say(role: str, work: str = "work-1") -> str:
    return agent_comment(work, role, "words")


ANNOUNCEMENT = "<!-- shelf:work-1 -->\n**A person is needed** (code_review)"
PROGRESS = "<!-- shelf-progress:work-1 -->\n### shelf-sdlc: progress"


def test_going_back_to_the_developer_hides_the_developers_old_comment_and_everything_after_it() -> None:
    comments = [
        posted(say("intake"), node="spec"),
        posted(say("planner"), node="plan"),
        posted(say("implementer"), node="dev"),
        posted(say("checks"), node="checks"),
        posted(say("code_reviewer"), node="review"),
    ]
    assert superseded(comments, "work-1", Phase.IMPLEMENT) == ["dev", "checks", "review"]


def test_what_came_before_the_phase_gone_back_to_still_holds() -> None:
    comments = [posted(say("intake"), node="spec"), posted(say("architect"), node="design")]
    assert superseded(comments, "work-1", Phase.IMPLEMENT) == []


def test_going_back_to_the_checks_keeps_the_developer_and_hides_the_checks_and_the_review() -> None:
    comments = [
        posted(say("implementer"), node="dev"),
        posted(say("checks"), node="c"),
        posted(say("code_reviewer"), node="r"),
    ]
    assert superseded(comments, "work-1", Phase.VERIFY) == ["c", "r"]


def test_a_wait_that_is_over_is_hidden_even_when_nothing_circled_back() -> None:
    comments = [posted(ANNOUNCEMENT, node="wait"), posted(say("implementer"), node="dev")]
    assert superseded(comments, "work-1", None) == ["wait"]


def test_the_progress_comment_and_what_people_wrote_are_never_touched() -> None:
    comments = [
        posted(PROGRESS, node="progress"),
        posted("/shelf changes rename it", node="command"),
        posted("looks good to me", node="person"),
        posted(agent_comment("work-1", "implementer", "x").replace("shelf-agent", "shelf-person"), node="via-shelf"),
    ]
    assert superseded(comments, "work-1", Phase.INTAKE) == []


def test_what_is_hidden_already_and_what_belongs_to_another_work_is_left_alone() -> None:
    comments = [
        posted(say("implementer"), hidden=True, node="done"),
        posted(say("implementer", "work-2"), node="other"),
        posted("<!-- shelf:work-2 -->\\nwait", node="other-wait"),
    ]
    assert superseded(comments, "work-1", Phase.IMPLEMENT) == []
