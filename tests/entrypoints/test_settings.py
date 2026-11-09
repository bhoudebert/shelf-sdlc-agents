from pathlib import Path

import pytest

from shelf.entrypoints.settings import MissingSettingError, from_environ

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
