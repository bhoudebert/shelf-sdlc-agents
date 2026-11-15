def test_an_agent_is_told_to_look_up_what_the_work_rests_on_and_to_follow_the_source() -> None:
    from shelf.domain.web import WEB_NOTE  # noqa: PLC0415

    assert "read from its documentation first" in WEB_NOTE
    assert "follow what you read and say so" in WEB_NOTE
    assert "open point for a person" in WEB_NOTE
