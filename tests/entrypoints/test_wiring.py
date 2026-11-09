import logging
from pathlib import Path

import pytest

from shelf.domain.polling import Mode
from shelf.entrypoints.settings import from_environ
from shelf.entrypoints.wiring import load_operator, pulse

BASE = {"PUBLIC_URL": "https://shelf.example.org", "SESSION_SECRET": "s" * 32}


def test_a_missing_operator_file_lets_nobody_in_and_says_so(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    settings = from_environ({**BASE, "SHELF_CONFIG": str(tmp_path / "absent.toml")})
    with caplog.at_level(logging.WARNING):
        operator = load_operator(settings)
    assert not operator.access.is_configured
    assert "NOBODY" in caplog.text


def test_the_operator_file_is_read_when_present(tmp_path: Path) -> None:
    path = tmp_path / "shelf.toml"
    path.write_text('mode = "server"\n[access]\nusers = ["alice"]\n')
    operator = load_operator(from_environ({**BASE, "SHELF_CONFIG": str(path)}))
    assert operator.mode is Mode.SERVER
    assert operator.access.users == frozenset({"alice"})


async def test_every_adapter_is_wired_to_its_port_without_reaching_out(tmp_path: Path) -> None:
    from unittest.mock import MagicMock  # noqa: PLC0415

    import httpx  # noqa: PLC0415

    from shelf.entrypoints.wiring import build_services  # noqa: PLC0415

    environ = {
        **BASE,
        "SHELF_CONFIG": str(tmp_path / "absent.toml"),
        "GITHUB_APP_ID": "1",
        "GITHUB_APP_PRIVATE_KEY": "pem",
        "GITHUB_APP_CLIENT_ID": "Iv1.x",
        "GITHUB_APP_CLIENT_SECRET": "cs",
        "GITHUB_APP_SLUG": "shelf",
        "GITHUB_WEBHOOK_SECRET": "ws",
        "SHELF_MODEL": "a-model",
    }
    settings = from_environ(environ)
    assert settings.github is not None
    async with httpx.AsyncClient() as client:
        services = build_services(settings, settings.github, client, MagicMock())
    assert services.runner.task_queue == "shelf"
    assert services.runner.mode is Mode.LOCAL
    assert services.steps.model == "a-model"


async def test_the_web_service_serves_the_registration_helper_until_the_app_exists() -> None:
    from shelf.entrypoints.web import build  # noqa: PLC0415

    app = await build(from_environ(BASE))
    assert app.title == "shelf-sdlc setup"


def test_an_invalid_operator_file_names_the_file_and_the_fix(tmp_path: Path) -> None:
    from shelf.domain.config import InvalidConfigError  # noqa: PLC0415

    path = tmp_path / "shelf.toml"
    path.write_text("[access]\nusers = [alice]\n")
    with pytest.raises(InvalidConfigError) as error:
        load_operator(from_environ({**BASE, "SHELF_CONFIG": str(path)}))
    assert str(path) in str(error.value)
    assert "quotes" in str(error.value)


def test_a_configuration_mistake_stops_the_program_with_one_readable_line() -> None:
    from shelf.entrypoints.settings import MissingSettingError, exit_with  # noqa: PLC0415

    with pytest.raises(SystemExit) as stop:
        exit_with(MissingSettingError("SESSION_SECRET is required"))
    assert str(stop.value) == "shelf: cannot start: SESSION_SECRET is required"


def test_the_heartbeat_outside_an_activity_does_nothing() -> None:
    pulse()
