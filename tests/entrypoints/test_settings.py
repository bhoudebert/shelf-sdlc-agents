from pathlib import Path

import pytest

from shelf.entrypoints.settings import ContainerSettings, MissingSettingError, from_environ

BASE = {"PUBLIC_URL": "https://shelf.example.org/", "SESSION_SECRET": "s" * 32}
APP = {
    "GITHUB_APP_ID": "1",
    "GITHUB_APP_PRIVATE_KEY": "-----BEGIN-----\\nabc\\n-----END-----",
    "GITHUB_APP_CLIENT_ID": "Iv1.x",
    "GITHUB_APP_CLIENT_SECRET": "secret",
    "GITHUB_APP_SLUG": "shelf",
    "GITHUB_WEBHOOK_SECRET": "hook",
}


def test_without_a_registered_app_the_settings_ask_for_setup_mode() -> None:
    settings = from_environ(BASE)
    assert settings.github is None
    assert settings.public_url == "https://shelf.example.org"
    assert settings.temporal_address == "temporal:7233"
    assert settings.task_queue == "shelf"
    assert (settings.max_turns, settings.max_budget_usd, settings.model, settings.port) == (40, None, None, 8080)


def test_a_registered_app_is_read_with_its_inline_key_unescaped() -> None:
    settings = from_environ({**BASE, **APP})
    assert settings.github is not None
    assert settings.github.private_key == "-----BEGIN-----\nabc\n-----END-----"
    assert settings.github.slug == "shelf"


def test_a_key_file_that_is_not_there_is_reported_where_to_put_it(tmp_path: Path) -> None:
    environ = {**BASE, **APP, "GITHUB_APP_PRIVATE_KEY_PATH": str(tmp_path / "absent.pem")}
    del environ["GITHUB_APP_PRIVATE_KEY"]
    with pytest.raises(MissingSettingError, match=r"deploy/secrets/github-app\.pem"):
        from_environ(environ)


def test_the_private_key_can_come_from_a_file(tmp_path: Path) -> None:
    key = tmp_path / "app.pem"
    key.write_text("PEM")
    environ = {**BASE, **APP, "GITHUB_APP_PRIVATE_KEY_PATH": str(key)}
    del environ["GITHUB_APP_PRIVATE_KEY"]
    settings = from_environ(environ)
    assert settings.github is not None
    assert settings.github.private_key == "PEM"


def test_a_missing_setting_says_where_to_find_it() -> None:
    environ = {**BASE, **APP}
    del environ["GITHUB_APP_SLUG"]
    with pytest.raises(MissingSettingError, match=r"github\.com/apps/<slug>"):
        from_environ(environ)


@pytest.mark.parametrize(
    ("remove", "message"),
    [
        ("PUBLIC_URL", "PUBLIC_URL is required"),
        ("SESSION_SECRET", "SESSION_SECRET is required"),
        ("GITHUB_APP_CLIENT_SECRET", "GITHUB_APP_CLIENT_SECRET is required"),
        ("GITHUB_APP_PRIVATE_KEY", "deploy/secrets/github-app.pem"),
    ],
)
def test_a_missing_setting_is_named(remove: str, message: str) -> None:
    environ = {**BASE, **APP}
    del environ[remove]
    with pytest.raises(MissingSettingError, match=message):
        from_environ(environ)


def test_the_nested_sandbox_is_off_unless_asked_for() -> None:
    assert not from_environ(BASE).nested_sandbox
    assert from_environ({**BASE, "SHELF_NESTED_SANDBOX": "1"}).nested_sandbox


def test_the_budget_and_the_model_are_read() -> None:
    settings = from_environ(
        {**BASE, "SHELF_MODEL": "claude-sonnet-5-5", "SHELF_MAX_BUDGET_USD": "2.5", "SHELF_MAX_TURNS": "12"}
    )
    assert (settings.model, settings.max_budget_usd, settings.max_turns) == ("claude-sonnet-5-5", 2.5, 12)


def test_the_revision_of_the_build_is_read_and_defaults_to_unknown() -> None:
    assert from_environ(BASE).revision == "unknown"
    assert from_environ({**BASE, "SHELF_REVISION": "abc1234"}).revision == "abc1234"


@pytest.mark.parametrize(
    "key", ["CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"]
)
def test_any_model_credential_counts(key: str) -> None:
    assert not from_environ(BASE).model_credential
    assert from_environ({**BASE, key: "x"}).model_credential
    assert not from_environ({**BASE, key: "  "}).model_credential


def test_the_sandbox_is_on_unless_the_operator_turns_it_off() -> None:
    assert from_environ(BASE).sandbox
    assert not from_environ({**BASE, "SHELF_SANDBOX_DISABLED": "1"}).sandbox


def test_the_cache_directory_and_extra_domains_are_read_from_the_environment() -> None:
    settings = from_environ(
        {**BASE, "SHELF_CACHE_DIR": "/cache", "SHELF_ALLOWED_DOMAINS": " nexus.example.org , ,b.org"}
    )
    assert settings.cache_dir == "/cache"
    assert settings.allowed_domains == ("nexus.example.org", "b.org")
    assert from_environ(BASE).cache_dir == ""
    assert from_environ(BASE).allowed_domains == ()


def test_the_time_given_to_the_ci_has_defaults_and_can_be_changed() -> None:
    assert (from_environ(BASE).ci_wait, from_environ(BASE).ci_grace) == (1800.0, 120.0)
    settings = from_environ({**BASE, "SHELF_CI_WAIT": "600", "SHELF_CI_GRACE": "0"})
    assert (settings.ci_wait, settings.ci_grace) == (600.0, 0.0)


def test_the_catalog_is_where_the_worker_mounts_it_unless_told_otherwise() -> None:
    assert from_environ(BASE).catalog_dir == Path("/opt/shelf/catalog")
    assert from_environ({**BASE, "SHELF_CATALOG_DIR": "/srv/catalog"}).catalog_dir == Path("/srv/catalog")


def test_agents_may_read_the_web_unless_the_operator_says_off() -> None:
    assert from_environ(BASE).web is True
    assert from_environ({**BASE, "SHELF_WEB": "on"}).web is True
    assert from_environ({**BASE, "SHELF_WEB": "OFF"}).web is False


def test_a_web_setting_that_is_not_on_or_off_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="SHELF_WEB must be on or off, not 'maybe'"):
        from_environ({**BASE, "SHELF_WEB": "maybe"})


def test_nix_is_off_unless_the_operator_says_on() -> None:
    assert from_environ(BASE).nix is False
    assert from_environ({**BASE, "SHELF_NIX": "on"}).nix is True
    assert from_environ({**BASE, "SHELF_NIX": "off"}).nix is False


def test_a_nix_setting_that_is_not_on_or_off_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="SHELF_NIX must be on or off, not 'maybe'"):
        from_environ({**BASE, "SHELF_NIX": "maybe"})


def test_agents_run_in_the_sandbox_unless_the_operator_says_otherwise() -> None:
    assert from_environ(BASE).isolation == "sandbox"
    assert from_environ({**BASE, "SHELF_ISOLATION": " Sandbox "}).isolation == "sandbox"


def test_an_unknown_isolation_is_refused_and_the_message_lists_the_choices() -> None:
    with pytest.raises(ValueError, match="sandbox, container"):
        from_environ({**BASE, "SHELF_ISOLATION": "vm"})


CONTAINER = {
    "SHELF_ISOLATION": "container",
    "SHELF_RUNNER_TOKEN": "t",
    "SHELF_STEPS_DIR": "/var/lib/shelf/steps",
    "SHELF_SESSIONS_DIR": "/var/lib/shelf/sessions",
    "SHELF_CACHE_DIR": "/cache",
}


def test_container_isolation_needs_the_runner_and_the_three_volumes_and_names_what_is_missing() -> None:
    with pytest.raises(MissingSettingError) as caught:
        from_environ({**BASE, "SHELF_ISOLATION": "container"})
    for name in ("SHELF_RUNNER_TOKEN", "SHELF_STEPS_DIR", "SHELF_SESSIONS_DIR", "SHELF_CACHE_DIR"):
        assert name in str(caught.value)


def test_container_isolation_with_everything_set_is_read_whole() -> None:
    settings = from_environ({**BASE, **CONTAINER})
    assert settings.isolation == "container"
    assert settings.container == ContainerSettings(
        "/run/shelf-runner/runner.sock", "t", Path("/var/lib/shelf/steps"), Path("/var/lib/shelf/sessions")
    )
    assert from_environ(BASE).container is None


def test_container_mode_carries_the_model_credential_the_worker_was_given_and_hides_it() -> None:
    settings = from_environ(
        {**BASE, **CONTAINER, "CLAUDE_CODE_OAUTH_TOKEN": " sk-credential ", "ANTHROPIC_API_KEY": ""}
    )
    assert settings.container is not None
    assert settings.container.model_env == (("CLAUDE_CODE_OAUTH_TOKEN", "sk-credential"),)
    assert "sk-credential" not in repr(settings)


def test_docker_in_steps_is_off_by_default() -> None:
    container = from_environ({**BASE, **CONTAINER}).container
    assert container is not None
    assert container.docker is False


def test_docker_in_steps_on_with_a_runtime_is_read() -> None:
    container = from_environ({**BASE, **CONTAINER, "SHELF_STEP_DOCKER": "on", "SHELF_STEP_RUNTIME": "kata"}).container
    assert container is not None
    assert container.docker is True


def test_docker_in_steps_on_without_a_runtime_is_refused_naming_the_runtime() -> None:
    with pytest.raises(MissingSettingError, match="SHELF_STEP_RUNTIME"):
        from_environ({**BASE, **CONTAINER, "SHELF_STEP_DOCKER": "on"})


def test_docker_in_steps_needs_the_container_mode() -> None:
    with pytest.raises(ValueError, match="SHELF_ISOLATION=container"):
        from_environ({**BASE, "SHELF_STEP_DOCKER": "on", "SHELF_STEP_RUNTIME": "kata"})


def test_docker_off_in_sandbox_mode_is_fine() -> None:
    assert from_environ({**BASE, "SHELF_STEP_DOCKER": "off"}).container is None


@pytest.mark.parametrize("value", ["yes", "private", "1"])
def test_a_docker_setting_that_is_not_on_or_off_is_refused_by_name(value: str) -> None:
    with pytest.raises(ValueError, match="SHELF_STEP_DOCKER"):
        from_environ({**BASE, **CONTAINER, "SHELF_STEP_DOCKER": value})


@pytest.mark.parametrize("value", ["privileged", "none", "Standard "])
def test_the_worker_refuses_a_profile_that_does_not_exist_by_name(value: str) -> None:
    env = {**BASE, **CONTAINER, "SHELF_STEP_DOCKER": "on", "SHELF_STEP_RUNTIME": "kata"}
    with pytest.raises(ValueError, match="SHELF_STEP_DOCKER_PROFILE"):
        from_environ({**env, "SHELF_STEP_DOCKER_PROFILE": value})


def test_the_worker_accepts_every_profile_the_runner_has() -> None:
    env = {**BASE, **CONTAINER, "SHELF_STEP_DOCKER": "on", "SHELF_STEP_RUNTIME": "kata"}
    for profile in ("standard", "unconfined", "cgroupns"):
        assert from_environ({**env, "SHELF_STEP_DOCKER_PROFILE": profile}).container is not None
