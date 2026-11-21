from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from shelf.domain.model import RepoRef
from shelf.domain.result import Err, Ok
from shelf.domain.stepspec import (
    DOCKER_CAPS,
    DOCKER_PROFILES,
    Limits,
    RunnerRules,
    StepAsk,
    container_spec,
    parse_request,
    tools_path,
)
from shelf.domain.toolchain import repository_home

RULES = RunnerRules(image="shelf-step:test")


def request(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "key": "wf-1/implement/2",
        "kind": "agent",
        "repo": "acme/shop",
        "clone": "steps/shelf-a1_b2/repo",
        "session": "work/wf-1",
        "env": {"ANTHROPIC_API_KEY": "sk-secret", "GH_TOKEN": "t"},
        "input": {"prompt": "go"},
    }
    return {**body, **changes}


def ask(**changes: Any) -> StepAsk:
    parsed = parse_request(request(**changes), RULES)
    assert isinstance(parsed, Ok), parsed
    return parsed.value


def refusal(**changes: Any) -> str:
    parsed = parse_request(request(**changes), RULES)
    assert isinstance(parsed, Err), parsed
    return parsed.error


def test_a_good_request_is_read_whole() -> None:
    step = ask()
    assert (step.key, step.kind, step.repo, step.clone, step.session) == (
        "wf-1/implement/2",
        "agent",
        "acme/shop",
        "steps/shelf-a1_b2/repo",
        "work/wf-1",
    )
    assert dict(step.env) == {"ANTHROPIC_API_KEY": "sk-secret", "GH_TOKEN": "t"}
    assert step.input == {"prompt": "go"}
    assert (step.tools_readonly, step.clone_readonly) == (False, False)


@pytest.mark.parametrize(
    "field", ["privileged", "mounts", "network", "user", "capabilities", "devices", "ports", "image", "extra"]
)
def test_a_field_that_is_an_engine_option_is_refused(field: str) -> None:
    assert field in refusal(**{field: "x"})


@pytest.mark.parametrize(
    ("changes", "named"),
    [
        ({"key": ""}, "key"),
        ({"key": "a b"}, "key"),
        ({"repo": "no-slash"}, "repo"),
        ({"repo": "a/b/c"}, "repo"),
        ({"clone": "steps/../etc"}, "clone"),
        ({"clone": "steps/a/b/repo"}, "clone"),
        ({"clone": "steps/a"}, "clone"),
        ({"env": {"WARDEN_PROFILE": "off"}}, "WARDEN_PROFILE"),
        ({"env": {"MISE_YES": "0"}}, "MISE_YES"),
        ({"clone": "/etc"}, "clone"),
        ({"clone": "volumes/x"}, "clone"),
        ({"session": "work/../x"}, "session"),
        ({"session": "other/x"}, "session"),
        ({"kind": "setup"}, "kind"),
        ({"mode": {"tools": "rwx"}}, "mode"),
        ({"mode": {"net": "rw"}}, "mode"),
        ({"limits": {"gpus": 1}}, "limits"),
        ({"limits": {"cpus": -1}}, "limit"),
        ({"env": {"PATH": "/x"}}, "PATH"),
        ({"env": {"LD_PRELOAD": "/x"}}, "LD_PRELOAD"),
        ({"env": {"lower": "x"}}, "env"),
        ({"env": {"GH_TOKEN": 1}}, "GH_TOKEN"),
        ({"input": "text"}, "input"),
    ],
)
def test_a_value_outside_the_rules_is_refused_and_named(changes: dict[str, Any], named: str) -> None:
    assert named in refusal(**changes)


def test_a_refusal_never_repeats_a_secret() -> None:
    message = refusal(env={"ANTHROPIC_API_KEY": "sk-secret", "PATH": "sk-secret"})
    assert "sk-secret" not in message
    assert "sk-secret" not in refusal(key="sk-secret and spaces")


def test_the_request_is_refused_when_it_is_not_an_object() -> None:
    assert isinstance(parse_request(["x"], RULES), Err)


def test_a_request_may_ask_for_less_than_the_ceiling_never_more() -> None:
    step = ask(limits={"cpus": 1, "memory_mb": 99_999_999, "seconds": 60})
    assert (step.limits.cpus, step.limits.memory_mb, step.limits.seconds) == (1.0, 6144, 60)
    assert step.limits.pids == RULES.limits.pids


@given(
    st.dictionaries(
        st.sampled_from(["cpus", "memory_mb", "pids", "tmp_mb", "seconds"]),
        st.integers(min_value=1, max_value=10**9),
    )
)
def test_clamped_limits_never_pass_the_ceiling(asked: dict[str, int]) -> None:
    ceiling = Limits()
    got = ceiling.clamped(asked)
    assert got.cpus <= ceiling.cpus
    assert (got.memory_mb, got.pids, got.tmp_mb, got.seconds) <= (
        ceiling.memory_mb,
        ceiling.pids,
        ceiling.tmp_mb,
        ceiling.seconds,
    )


def spec(**changes: Any) -> dict[str, Any]:
    return container_spec(ask(**changes), RULES, expires=1_000)


def test_the_container_is_locked_down_whatever_the_request_says() -> None:
    body = spec()
    host = body["HostConfig"]
    assert body["User"] == "1000:1000"
    assert (host["ReadonlyRootfs"], host["CapDrop"], host["SecurityOpt"]) == (True, ["ALL"], ["no-new-privileges"])
    assert (host["Privileged"], host["Init"], host["PublishAllPorts"], host["AutoRemove"]) == (
        False,
        True,
        False,
        False,
    )
    assert host["NetworkMode"] == "shelf-step"
    assert "Binds" not in host
    assert "PortBindings" not in host
    assert "Devices" not in host
    assert "PidMode" not in host


def test_every_mount_is_a_named_volume_never_a_host_path() -> None:
    mounts = spec()["HostConfig"]["Mounts"]
    assert {mount["Type"] for mount in mounts} == {"volume"}
    sources = {mount.get("Source", "") for mount in mounts}
    assert sources <= {"shelf-steps", "shelf-tools", "shelf-sessions", ""}
    assert not any(str(source).startswith("/") for source in sources)


def test_the_clone_tools_and_sessions_mount_in_their_places() -> None:
    mounts = {m["Target"]: m for m in spec()["HostConfig"]["Mounts"]}
    assert mounts["/work"]["VolumeOptions"] == {"Subpath": "steps/shelf-a1_b2/repo"}
    assert mounts["/home/step/.m2"]["VolumeOptions"] == {"Subpath": "home/acme__shop/.m2"}
    assert mounts["/home/step/.local/share/mise"]["Source"] == "shelf-tools"
    assert mounts["/home/step/.claude/projects"]["VolumeOptions"] == {"Subpath": "work/wf-1"}
    assert mounts["/home/step/.local/share/mise"]["VolumeOptions"] == {"Subpath": "home/acme__shop/.local/share/mise"}
    assert mounts["/run/shelf"].get("Source") is None


def test_a_reviewer_gets_its_tools_read_only() -> None:
    mounts = {m["Target"]: m for m in spec(mode={"tools": "ro"})["HostConfig"]["Mounts"]}
    assert mounts["/home/step/.m2"]["ReadOnly"] is True
    assert mounts["/work"]["ReadOnly"] is False
    assert mounts["/home/step/.claude/projects"]["ReadOnly"] is False


def test_a_step_without_a_session_gets_no_sessions_mount() -> None:
    targets = {m["Target"] for m in spec(session="")["HostConfig"]["Mounts"]}
    assert "/home/step/.claude/projects" not in targets


def test_the_limits_become_engine_limits() -> None:
    host = spec(limits={"cpus": 2, "memory_mb": 1024, "pids": 100, "tmp_mb": 64})["HostConfig"]
    assert host["NanoCpus"] == 2_000_000_000
    assert host["Memory"] == host["MemorySwap"] == 1024 * 1024 * 1024
    assert host["PidsLimit"] == 100
    assert host["Tmpfs"] == {"/tmp": "rw,nosuid,size=64m"}  # noqa: S108


def test_the_container_carries_labels_so_a_restart_can_find_it() -> None:
    assert spec()["Labels"] == {"shelf.managed": "true", "shelf.step": "wf-1/implement/2", "shelf.expires": "1000"}


def test_the_environment_holds_what_the_request_gave_and_a_home() -> None:
    env = spec()["Env"]
    assert "ANTHROPIC_API_KEY=sk-secret" in env
    assert "HOME=/home/step" in env


def test_the_command_reads_the_task_from_the_file_the_runner_puts_there() -> None:
    assert spec()["Cmd"] == ["shelf-step", "/run/shelf/task.json"]


def test_tools_of_one_repository_never_collide_with_another() -> None:
    assert tools_path("a/b__c") == "home/a__b__c"
    assert "repo" in refusal(repo="a__b/c")


def test_the_tools_folder_is_the_one_the_workers_own_setup_uses() -> None:
    assert repository_home("/cache", RepoRef("acme", "shop")) == f"/cache/{tools_path('acme/shop')}"


RULES_WITH_CONFIG = RunnerRules(
    image="shelf-step:test",
    config=(("shelf-policy", "/etc/claude-code"), ("shelf-catalog", "/opt/shelf/catalog")),
    fixed_env=(("WARDEN_PROFILE", "shelf"),),
)


def test_the_config_volumes_are_mounted_read_only_where_the_product_reads_them() -> None:
    body = container_spec(ask(), RULES_WITH_CONFIG, expires=1)
    mounts = {m["Target"]: m for m in body["HostConfig"]["Mounts"]}
    for target, volume in (("/etc/claude-code", "shelf-policy"), ("/opt/shelf/catalog", "shelf-catalog")):
        assert (mounts[target]["Source"], mounts[target]["ReadOnly"]) == (volume, True)
        assert "VolumeOptions" not in mounts[target]


def test_the_operators_variables_and_the_tool_installers_are_set_in_every_step() -> None:
    env = container_spec(ask(), RULES_WITH_CONFIG, expires=1)["Env"]
    assert "WARDEN_PROFILE=shelf" in env
    assert {"MISE_YES=1", "MISE_LOCKFILE=false", "MISE_TRUSTED_CONFIG_PATHS=/work"} <= set(env)
    assert any(item.startswith("MISE_DISABLE_BACKENDS=") for item in env)


DOCKER_RULES = RunnerRules(image="shelf-step:test", docker_image="shelf-step-docker:test", docker_runtime="kata")


def docker_ask(**changes: Any) -> StepAsk:
    parsed = parse_request(request(docker=True, **changes), DOCKER_RULES)
    assert isinstance(parsed, Ok), parsed
    return parsed.value


def test_a_step_has_no_docker_unless_the_request_says_so() -> None:
    assert ask().docker is False
    assert docker_ask().docker is True


def test_docker_is_refused_by_a_runner_that_has_no_runtime_for_it() -> None:
    assert "docker" in refusal(docker=True)


@pytest.mark.parametrize("value", ["yes", 1, None, ["x"]])
def test_docker_must_be_true_or_false(value: object) -> None:
    parsed = parse_request(request(docker=value), DOCKER_RULES)
    assert isinstance(parsed, Err)
    assert "docker" in parsed.error


@pytest.mark.parametrize("field", ["mounts", "privileged", "devices", "capabilities", "runtime", "image"])
def test_docker_is_the_only_field_a_request_may_add_for_it(field: str) -> None:
    parsed = parse_request(request(docker=True, **{field: "x"}), DOCKER_RULES)
    assert isinstance(parsed, Err)
    assert field in parsed.error


def docker_spec(**changes: Any) -> dict[str, Any]:
    return container_spec(docker_ask(**changes), DOCKER_RULES, expires=1_000)


def test_a_step_with_docker_runs_under_the_runtime_the_operator_named_and_is_not_privileged_on_the_host() -> None:
    body = docker_spec()
    host = body["HostConfig"]
    assert host["Runtime"] == "kata"
    assert host["Privileged"] is False
    assert body["Image"] == "shelf-step-docker:test"
    assert "Binds" not in host
    assert "Devices" not in host
    assert "PidMode" not in host
    assert host["NetworkMode"] == "shelf-step"
    assert host["PublishAllPorts"] is False


def test_a_step_with_docker_never_gets_the_engine_socket_or_a_host_path() -> None:
    mounts = docker_spec()["HostConfig"]["Mounts"]
    assert {mount["Type"] for mount in mounts} == {"volume"}
    assert not any("docker.sock" in mount["Target"] for mount in mounts)
    assert {mount.get("Source", "") for mount in mounts} <= {"shelf-steps", "shelf-tools", "shelf-sessions", ""}


def test_the_daemons_storage_is_a_volume_of_the_step_that_goes_with_it() -> None:
    mounts = docker_spec()["HostConfig"]["Mounts"]
    storage = [mount for mount in mounts if mount["Target"] == "/var/lib/docker"]
    assert len(storage) == 1
    assert "Source" not in storage[0]  # anonymous: removed with the container


def test_a_step_with_docker_starts_through_the_wrapper_that_starts_the_daemon() -> None:
    assert docker_spec()["Cmd"][0] == "shelf-step-docker"
    assert spec()["Cmd"][0] == "shelf-step"


def test_a_step_without_docker_is_built_exactly_as_before() -> None:
    body = container_spec(ask(), DOCKER_RULES, expires=1_000)
    assert body == container_spec(ask(), RULES, expires=1_000) | {"Image": "shelf-step:test"}
    assert "Runtime" not in body["HostConfig"]


def test_the_limits_of_the_step_cover_what_its_daemon_starts() -> None:
    host = docker_spec(limits={"memory_mb": 1024, "pids": 100})["HostConfig"]
    assert host["Memory"] == 1024 * 1024 * 1024
    assert host["PidsLimit"] == 100


def profile_rules(profile: str) -> RunnerRules:
    return RunnerRules(
        image="shelf-step:test", docker_image="shelf-step-docker:test", docker_runtime="kata", docker_profile=profile
    )


def profile_host(profile: str) -> dict[str, Any]:
    parsed = parse_request(request(docker=True), profile_rules(profile))
    assert isinstance(parsed, Ok)
    return container_spec(parsed.value, profile_rules(profile), expires=1)["HostConfig"]


def test_the_standard_profile_is_the_default_and_lifts_nothing() -> None:
    assert RunnerRules(image="x").docker_profile == "standard"
    host = profile_host("standard")
    assert host["SecurityOpt"] == ["no-new-privileges"]
    assert "CgroupnsMode" not in host
    assert host["CapAdd"] == list(DOCKER_CAPS)


def test_the_unconfined_profile_lifts_the_guests_seccomp_and_apparmor_and_nothing_else() -> None:
    host = profile_host("unconfined")
    assert host["SecurityOpt"] == ["no-new-privileges", "seccomp=unconfined", "apparmor=unconfined"]
    assert "CgroupnsMode" not in host


def test_the_systempaths_profile_also_lifts_the_read_only_and_masked_system_paths() -> None:
    host = profile_host("systempaths")
    assert host["SecurityOpt"] == [
        "no-new-privileges",
        "seccomp=unconfined",
        "apparmor=unconfined",
        "systempaths=unconfined",
    ]
    assert "CgroupnsMode" not in host
    assert host["CapAdd"] == list(DOCKER_CAPS)


def test_the_full_profile_is_everything_privileged_mode_gives_except_the_hosts_devices() -> None:
    host = profile_host("full")
    assert host["SecurityOpt"] == [
        "no-new-privileges",
        "seccomp=unconfined",
        "apparmor=unconfined",
        "systempaths=unconfined",
    ]
    assert host["CgroupnsMode"] == "host"
    assert host["CapAdd"] == [*DOCKER_CAPS, "ALL"]
    assert host["Privileged"] is False
    assert "Devices" not in host


def test_each_profile_adds_to_the_one_before_it() -> None:
    previous: set[str] = set()
    for profile in DOCKER_PROFILES:
        host = profile_host(profile)
        options: list[str] = host["SecurityOpt"]
        caps: list[str] = host["CapAdd"]
        now = {*options, *caps, *(["cgroupns"] if "CgroupnsMode" in host else [])}
        assert previous <= now, profile
        previous = now


@pytest.mark.parametrize("profile", DOCKER_PROFILES)
def test_no_profile_is_privileged_or_gives_a_device_a_host_path_or_the_engine_socket(profile: str) -> None:
    host = profile_host(profile)
    assert host["Privileged"] is False
    assert "Devices" not in host
    assert "Binds" not in host
    assert {m["Type"] for m in host["Mounts"]} == {"volume"}
    assert not any("docker.sock" in m["Target"] for m in host["Mounts"])
    assert host["Runtime"] == "kata"


def test_a_step_without_docker_is_the_same_under_every_profile() -> None:
    plain = container_spec(ask(), profile_rules("standard"), expires=1)
    for profile in DOCKER_PROFILES:
        assert container_spec(ask(), profile_rules(profile), expires=1) == plain


def check_request(**changes: Any) -> dict[str, Any]:
    body = request(kind="check", env={}, session="", input={"command": "./mvnw -B verify"})
    return {**body, **changes}


def check_ask(**changes: Any) -> StepAsk:
    parsed = parse_request(check_request(**changes), RULES)
    assert isinstance(parsed, Ok), parsed
    return parsed.value


def test_a_check_is_a_kind_the_runner_runs() -> None:
    assert check_ask().kind == "check"


@pytest.mark.parametrize("variable", ["ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"])
def test_a_check_is_never_given_a_credential(variable: str) -> None:
    parsed = parse_request(check_request(env={variable: "secret-value"}), RULES)
    assert isinstance(parsed, Err)
    assert variable in parsed.error
    assert "secret-value" not in parsed.error


def test_a_check_may_be_given_the_variables_that_are_not_credentials() -> None:
    assert check_ask(env={"SHELF_STEP_X": "1"}).env == {"SHELF_STEP_X": "1"}


@pytest.mark.parametrize("command", ["", "   ", None, 5, ["a"], "x" * 4001, "a\x00b"])
def test_a_check_needs_a_command_that_is_text_of_a_sane_size(command: object) -> None:
    parsed = parse_request(check_request(input={"command": command}), RULES)
    assert isinstance(parsed, Err)
    assert "command" in parsed.error


def test_a_check_is_built_like_an_agent_step_and_runs_its_own_program() -> None:
    body = container_spec(check_ask(), RULES, expires=1_000)
    assert body["Cmd"] == ["shelf-check", "/run/shelf/task.json"]
    assert body["User"] == "1000:1000"
    assert body["HostConfig"]["CapDrop"] == ["ALL"]
    assert [m for m in body["HostConfig"]["Mounts"] if m["Target"].endswith("/projects")] == []
    tools = [m for m in body["HostConfig"]["Mounts"] if m["Target"].endswith("/.m2")]
    assert tools[0]["ReadOnly"] is False


def test_a_check_with_docker_runs_its_program_through_the_wrapper() -> None:
    parsed = parse_request(check_request(docker=True), DOCKER_RULES)
    assert isinstance(parsed, Ok)
    assert container_spec(parsed.value, DOCKER_RULES, expires=1)["Cmd"] == [
        "shelf-step-docker",
        "shelf-check",
        "/run/shelf/task.json",
    ]
    assert docker_spec()["Cmd"] == ["shelf-step-docker", "shelf-step", "/run/shelf/task.json"]


def test_an_unknown_kind_is_still_refused() -> None:
    parsed = parse_request(request(kind="setup"), RULES)
    assert isinstance(parsed, Err)
    assert "kind" in parsed.error
