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


def test_every_role_gets_the_normal_toolset_and_the_sandbox() -> None:
    options = options_for(task(Phase.CODE_REVIEW))
    assert set(options.allowed_tools) == {"Read", "Glob", "Grep", "Write", "Edit", "Bash"}
    assert options.sandbox is not None
    assert options.sandbox.get("enabled") is True


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


def test_the_sandbox_can_be_turned_off_where_it_cannot_start() -> None:
    assert options_for(task(Phase.IMPLEMENT), sandbox=False).sandbox.get("enabled") is False  # type: ignore[union-attr]
    assert options_for(task(Phase.IMPLEMENT)).sandbox.get("enabled") is True  # type: ignore[union-attr]


def test_the_agents_use_claude_codes_defaults_with_our_role_prompt_appended() -> None:
    options = options_for(task(Phase.CODE_REVIEW))
    assert options.system_prompt == {"type": "preset", "preset": "claude_code", "append": "system"}


def test_the_repositorys_own_agent_files_are_loaded_but_never_its_hooks_or_mcp_servers() -> None:
    options = options_for(task(Phase.CODE_REVIEW))
    assert options.setting_sources == ["project"]
    assert options.settings == '{"disableAllHooks": true}'
    assert options.strict_mcp_config


def test_a_specific_claude_executable_can_be_used() -> None:
    assert (
        options_for(task(Phase.IMPLEMENT), cli_path="/home/ubuntu/.local/bin/claude").cli_path
        == "/home/ubuntu/.local/bin/claude"
    )


def test_the_workers_secrets_are_blanked_for_the_agent_but_what_it_needs_is_left_alone() -> None:
    from shelf.adapters.claude_agent.backend import hidden_from_agents  # noqa: PLC0415

    environ = {
        "PATH": "/usr/bin",
        "HOME": "/home/shelf",
        "CLAUDE_CODE_OAUTH_TOKEN": "needed",
        "GITHUB_APP_CLIENT_SECRET": "s",
        "GITHUB_APP_PRIVATE_KEY": "k",
        "GITHUB_WEBHOOK_SECRET": "w",
        "SESSION_SECRET": "x",
    }
    assert hidden_from_agents(environ) == {
        "GITHUB_APP_CLIENT_SECRET": "",
        "GITHUB_APP_PRIVATE_KEY": "",
        "GITHUB_WEBHOOK_SECRET": "",
        "SESSION_SECRET": "",
    }


def test_an_agents_options_override_the_inherited_secrets_and_keep_what_the_step_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SESSION_SECRET", "leak")
    monkeypatch.setenv("GITHUB_APP_ID", "123")
    options = options_for(task(Phase.IMPLEMENT))
    assert options.env["SESSION_SECRET"] == ""
    assert options.env["GITHUB_APP_ID"] == ""
    assert options.env["GH_TOKEN"] == "t"  # what the step passes is kept
