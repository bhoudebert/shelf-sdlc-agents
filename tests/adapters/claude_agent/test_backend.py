from pathlib import Path

import pytest

from shelf.adapters.claude_agent.backend import AgentFailedError, options_for
from shelf.adapters.claude_agent.prompts import load_prompt
from shelf.domain.pipeline import Phase
from shelf.domain.roles import ROLES
from shelf.ports.agents import AgentTask


def task(phase: Phase) -> AgentTask:
    return AgentTask(
        ROLES[phase], "system", "prompt", Path("/clone"), {"GH_TOKEN": "t"}, max_turns=7, max_budget_usd=1.5, model="m"
    )


def test_a_role_gets_only_its_own_tools_and_the_sandbox() -> None:
    options = options_for(task(Phase.CODE_REVIEW))
    assert options.allowed_tools == ["Read", "Glob", "Grep"]
    assert options.sandbox is not None
    assert options.sandbox.get("enabled") is True
    assert options.setting_sources == []


def test_the_budget_the_model_and_the_environment_are_passed_through() -> None:
    options = options_for(task(Phase.IMPLEMENT))
    assert (options.max_turns, options.max_budget_usd, options.model) == (7, 1.5, "m")
    assert options.env == {"GH_TOKEN": "t"}
    assert str(options.cwd) == "/clone"
    assert "Bash" in options.allowed_tools


@pytest.mark.parametrize("phase", list(ROLES))
def test_every_role_has_a_system_prompt(phase: Phase) -> None:
    assert load_prompt(ROLES[phase].name).strip()


def test_every_reviewer_prompt_defines_the_verdict_line() -> None:
    for phase in (Phase.SPEC_REVIEW, Phase.DESIGN_REVIEW, Phase.CODE_REVIEW):
        assert "VERDICT: APPROVE" in load_prompt(ROLES[phase].name)


def test_a_login_failure_tells_the_operator_where_the_credential_goes() -> None:
    message = str(AgentFailedError("intake", "Not logged in · Please run /login"))
    assert "CLAUDE_CODE_OAUTH_TOKEN" in message
    assert "deploy/.env" in message
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in str(AgentFailedError("intake", "max turns reached"))


def test_the_nested_sandbox_is_opt_in_for_containers() -> None:
    assert options_for(task(Phase.IMPLEMENT)).sandbox.get("enableWeakerNestedSandbox") is False  # type: ignore[union-attr]
    assert options_for(task(Phase.IMPLEMENT), nested_sandbox=True).sandbox.get("enableWeakerNestedSandbox") is True  # type: ignore[union-attr]
