import json
import logging
from pathlib import Path

import pytest
from claude_agent_sdk import ResultMessage

from shelf.adapters.claude_agent.backend import AgentFailedError, ClaudeBackend, options_for, step_summary
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
    assert options.env["GH_TOKEN"] == "t"
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


def test_the_sandbox_may_reach_only_the_sites_it_is_given() -> None:
    options = options_for(task(Phase.IMPLEMENT), allowed_domains=("github.com", "repo.maven.apache.org"))
    assert options.sandbox is not None
    assert options.sandbox.get("network") == {"allowedDomains": ["github.com", "repo.maven.apache.org"]}


def test_an_agent_starts_with_telemetry_and_automatic_memory_off() -> None:
    env = options_for(task(Phase.IMPLEMENT)).env
    assert env["DO_NOT_TRACK"] == "1"
    assert env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"


def test_a_steps_own_environment_may_override_the_defaults() -> None:
    step = task(Phase.IMPLEMENT)
    other = AgentTask(
        step.role, "s", "p", Path("/clone"), {"DO_NOT_TRACK": "0"}, max_turns=1, max_budget_usd=None, model=None
    )
    assert options_for(other).env["DO_NOT_TRACK"] == "0"


def catalog(tmp_path: Path, *names: str) -> Path:
    for name in names:
        (tmp_path / name / ".claude-plugin").mkdir(parents=True)
        (tmp_path / name / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}))
    return tmp_path


def bound(tmp_path: Path, mapping: dict[str, tuple[str, ...]]) -> ClaudeBackend:
    return ClaudeBackend(
        catalog_dir=catalog(tmp_path, "superpowers", "gdpr"), bindings=lambda role: mapping.get(role, ())
    )


def test_a_role_loads_the_bundles_bound_to_it_and_other_roles_do_not(tmp_path: Path) -> None:
    backend = bound(tmp_path, {"implementer": ("superpowers",)})
    implementer = backend.options(task(Phase.IMPLEMENT))
    critic = backend.options(task(Phase.SPEC_REVIEW))
    assert implementer.plugins == [{"type": "local", "path": str(tmp_path / "superpowers")}]
    assert critic.plugins == []


def test_a_bound_name_the_catalog_lacks_is_skipped_and_named(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    backend = bound(tmp_path, {"implementer": ("superpowers", "ghost")})
    with caplog.at_level(logging.WARNING):
        options = backend.options(task(Phase.IMPLEMENT))
    assert [plugin["path"] for plugin in options.plugins] == [str(tmp_path / "superpowers")]
    assert "ghost" in caplog.text


def test_without_a_catalog_or_bindings_agents_start_with_no_extra_plugin(tmp_path: Path) -> None:
    assert ClaudeBackend().options(task(Phase.IMPLEMENT)).plugins == []
    assert ClaudeBackend(catalog_dir=tmp_path).options(task(Phase.IMPLEMENT)).plugins == []
    empty = ClaudeBackend(catalog_dir=tmp_path / "absent", bindings=lambda _role: ("superpowers",))
    assert empty.options(task(Phase.IMPLEMENT)).plugins == []


def _result(**changes: object) -> ResultMessage:
    fields: dict[str, object] = {
        "subtype": "success",
        "duration_ms": 94_000,
        "duration_api_ms": 80_000,
        "is_error": False,
        "num_turns": 12,
        "session_id": "s",
        "total_cost_usd": 0.4213,
        "result": "the secret answer",
    }
    return ResultMessage(**{**fields, **changes})  # pyright: ignore[reportArgumentType]


def test_a_finished_step_is_summarised_in_one_line_without_its_answer() -> None:
    line = step_summary("code_reviewer", _result())
    assert line == "agent step finished: role=code_reviewer turns=12 seconds=94 cost=$0.4213"
    assert "secret" not in line


def test_a_missing_cost_is_unknown_not_zero() -> None:
    assert "cost=unknown" in step_summary("planner", _result(total_cost_usd=None))


def test_refused_tool_calls_are_counted_when_there_are_any() -> None:
    line = step_summary("implementer", _result(permission_denials=[{"tool_name": "Bash"}, {"tool_name": "Bash"}]))
    assert line.endswith("refused_tool_calls=2")
