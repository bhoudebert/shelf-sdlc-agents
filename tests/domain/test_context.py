from shelf.domain.context import CATEGORIES, LIMIT, context_brief


def test_a_repository_with_nothing_to_respect_gets_no_brief() -> None:
    assert context_brief({title: [] for title in CATEGORIES}, []) == ""


def test_the_brief_lists_what_exists_under_its_kind_and_tells_the_agent_not_to_contradict_it() -> None:
    brief = context_brief(
        {"Existing specifications (the contract: do not contradict them)": ["openspec/specs/pipeline/spec.md"]},
        ["docs/shelf/work-0/spec.md"],
    )
    assert "Existing specifications" in brief
    assert "- openspec/specs/pipeline/spec.md" in brief
    assert "Specs of earlier work" in brief
    assert "- docs/shelf/work-0/spec.md" in brief
    assert "must not contradict" in brief


def test_a_long_list_is_cut_so_the_prompt_stays_readable() -> None:
    paths = [f"docs/adr/{n:04d}.md" for n in range(100)]
    assert context_brief({"ADRs": paths}, []).count("- docs/adr/") == LIMIT
