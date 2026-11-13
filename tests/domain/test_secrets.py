from shelf.domain.secrets import for_commands, hidden_from_agents, is_worker_secret

ENVIRON = {
    "PATH": "/usr/bin",
    "HOME": "/home/shelf",
    "CLAUDE_CODE_OAUTH_TOKEN": "model",
    "ANTHROPIC_API_KEY": "key",
    "GITHUB_APP_CLIENT_SECRET": "s",
    "GITHUB_APP_PRIVATE_KEY_PATH": "/run/secrets/github-app.pem",
    "GITHUB_WEBHOOK_SECRET": "w",
    "SESSION_SECRET": "x",
}


def test_the_worker_secrets_are_the_session_and_webhook_secrets_and_every_app_setting() -> None:
    assert all(
        is_worker_secret(name)
        for name in ("SESSION_SECRET", "GITHUB_WEBHOOK_SECRET", "GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY_PATH")
    )
    assert not any(is_worker_secret(name) for name in ("PATH", "HOME", "CLAUDE_CODE_OAUTH_TOKEN"))


def test_an_agent_loses_the_worker_secrets_but_keeps_the_model_credential() -> None:
    assert set(hidden_from_agents(ENVIRON)) == {
        "GITHUB_APP_CLIENT_SECRET",
        "GITHUB_APP_PRIVATE_KEY_PATH",
        "GITHUB_WEBHOOK_SECRET",
        "SESSION_SECRET",
    }
    assert set(hidden_from_agents(ENVIRON).values()) == {""}


def test_a_repositorys_commands_lose_the_worker_secrets_and_the_model_credential() -> None:
    assert for_commands(ENVIRON) == {"PATH": "/usr/bin", "HOME": "/home/shelf"}
