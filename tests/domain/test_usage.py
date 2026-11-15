from shelf.domain.usage import StepUsage, Usage, summarize


def used(tokens: int, cost: float | None = 0.1, turns: int = 2, seconds: float = 10.0, model: str = "m") -> Usage:
    return Usage(tokens, tokens // 10, tokens * 2, tokens // 5, cost, turns, seconds, (model,))


def test_the_tokens_of_a_step_are_all_the_tokens_the_provider_counted() -> None:
    assert Usage(1000, 100, 2000, 200).tokens == 3300


def test_two_uses_add_up_and_a_cost_the_provider_did_not_report_is_not_zero() -> None:
    both = used(100, 0.5) + used(100, None)
    assert both.cost_usd == 0.5
    assert (used(100, None) + used(100, None)).cost_usd is None
    assert both.turns == 4
    assert both.models == ("m",)


def test_the_steps_of_a_work_are_summed_per_agent_in_the_order_each_first_ran_and_for_the_whole() -> None:
    steps = [
        StepUsage("intake", 0, "intake", used(1000, 0.4)),
        StepUsage("spec_review", 0, "spec_critic", used(500, 0.2)),
        StepUsage("intake", 1, "intake", used(800, 0.3)),
        StepUsage("spec_review", 1, "spec_critic", used(500, 0.2)),
        StepUsage("intake", 2, "intake", used(700, 0.2)),
    ]
    summary = summarize(steps)
    assert [a.agent for a in summary.agents] == ["intake", "spec_critic"]
    intake = summary.agents[0]
    assert intake.runs == 3
    assert intake.usage.input_tokens == 2500
    assert round(intake.usage.cost_usd or 0, 2) == 0.9
    assert round(summary.total.cost_usd or 0, 2) == 1.3
    assert summary.steps == tuple(steps)


def test_a_work_with_no_step_has_an_empty_summary() -> None:
    summary = summarize([])
    assert summary.agents == ()
    assert summary.total == Usage()
