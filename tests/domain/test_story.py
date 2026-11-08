from shelf.domain.story import SPEAKERS, Voice, agent_comment, classify, person_comment


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
