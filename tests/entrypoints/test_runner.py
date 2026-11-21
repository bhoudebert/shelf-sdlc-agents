import pytest

from shelf.entrypoints.runner import RunnerSettingsError, check_runtime, read_settings
from tests.adapters.container_runner.fakes import FakeEngine

GOOD = {"SHELF_STEP_IMAGE": "shelf-step:1", "SHELF_RUNNER_TOKEN": "secret"}


def test_the_image_and_the_token_are_all_it_needs() -> None:
    settings = read_settings(GOOD)
    assert settings.token == "secret"
    assert settings.rules.image == "shelf-step:1"
    assert settings.socket == "/run/shelf-runner/runner.sock"
    assert settings.rules.limits.seconds == 2700


def test_without_an_image_it_does_not_start() -> None:
    with pytest.raises(RunnerSettingsError, match="SHELF_STEP_IMAGE"):
        read_settings({"SHELF_RUNNER_TOKEN": "secret"})


def test_without_a_token_it_does_not_start_and_the_message_says_a_token_is_needed() -> None:
    with pytest.raises(RunnerSettingsError, match="SHELF_RUNNER_TOKEN is needed"):
        read_settings({"SHELF_STEP_IMAGE": "x"})


def test_only_the_explicit_variable_lets_it_run_without_a_token() -> None:
    assert read_settings({"SHELF_STEP_IMAGE": "x", "SHELF_RUNNER_INSECURE": "1"}).token is None
    with pytest.raises(RunnerSettingsError):
        read_settings({"SHELF_STEP_IMAGE": "x", "SHELF_RUNNER_INSECURE": "yes"})


def test_the_operator_sets_the_ceilings_and_the_volumes() -> None:
    settings = read_settings(
        {
            **GOOD,
            "SHELF_STEP_CPUS": "2",
            "SHELF_STEP_MEMORY_MB": "1024",
            "SHELF_STEPS_VOLUME": "mine",
            "SHELF_STEP_NETWORK": "n",
        }
    )
    assert (settings.rules.limits.cpus, settings.rules.limits.memory_mb) == (2.0, 1024)
    assert (settings.rules.steps_volume, settings.rules.network) == ("mine", "n")


@pytest.mark.parametrize("value", ["lots", "0", "-3"])
def test_a_ceiling_that_is_not_a_positive_number_is_refused_by_name(value: str) -> None:
    with pytest.raises(RunnerSettingsError, match="SHELF_STEP_CPUS") as caught:
        read_settings({**GOOD, "SHELF_STEP_CPUS": value})
    assert "secret" not in str(caught.value)


def test_the_config_volumes_and_the_fixed_variables_come_from_the_operator() -> None:
    settings = read_settings(
        {
            **GOOD,
            "SHELF_STEP_CONFIG": "pol:/etc/claude-code, cat:/opt/shelf/catalog",
            "SHELF_STEP_SET_WARDEN_PROFILE": "shelf",
        }
    )
    assert settings.rules.config == (("pol", "/etc/claude-code"), ("cat", "/opt/shelf/catalog"))
    assert settings.rules.fixed_env == (("WARDEN_PROFILE", "shelf"),)


@pytest.mark.parametrize("config", ["pol:/etc/passwd", "pol", ":/etc/claude-code", "pol:/"])
def test_a_config_volume_may_only_go_where_the_product_reads_config(config: str) -> None:
    with pytest.raises(RunnerSettingsError, match="SHELF_STEP_CONFIG"):
        read_settings({**GOOD, "SHELF_STEP_CONFIG": config})


def test_a_fixed_variable_with_a_bad_name_is_refused_without_its_value() -> None:
    with pytest.raises(RunnerSettingsError, match="not a variable name") as caught:
        read_settings({**GOOD, "SHELF_STEP_SET_bad": "sk-secret"})
    assert "sk-secret" not in str(caught.value)


def test_docker_in_steps_is_off_unless_the_operator_turns_it_on() -> None:
    rules = read_settings(GOOD).rules
    assert rules.docker_runtime == ""


@pytest.mark.parametrize("value", ["yes", "1", "true", "private"])
def test_a_docker_setting_that_is_not_on_or_off_is_refused_by_name(value: str) -> None:
    with pytest.raises(RunnerSettingsError, match="SHELF_STEP_DOCKER"):
        read_settings({**GOOD, "SHELF_STEP_DOCKER": value})


def test_docker_on_without_a_runtime_does_not_start_and_says_a_runtime_must_be_named() -> None:
    with pytest.raises(RunnerSettingsError, match="SHELF_STEP_RUNTIME"):
        read_settings({**GOOD, "SHELF_STEP_DOCKER": "on"})


def test_docker_on_with_a_runtime_is_in_the_rules_and_the_image_defaults_to_the_step_image() -> None:
    rules = read_settings({**GOOD, "SHELF_STEP_DOCKER": "on", "SHELF_STEP_RUNTIME": "kata"}).rules
    assert (rules.docker_runtime, rules.docker_image) == ("kata", "shelf-step:1")
    other = read_settings(
        {
            **GOOD,
            "SHELF_STEP_DOCKER": "on",
            "SHELF_STEP_RUNTIME": "kata",
            "SHELF_STEP_DOCKER_IMAGE": "shelf-step-docker:1",
        }
    ).rules
    assert other.docker_image == "shelf-step-docker:1"


def test_a_runtime_without_docker_on_is_ignored() -> None:
    assert read_settings({**GOOD, "SHELF_STEP_RUNTIME": "kata"}).rules.docker_runtime == ""


async def test_the_engine_must_have_the_runtime_the_operator_named() -> None:
    rules = read_settings({**GOOD, "SHELF_STEP_DOCKER": "on", "SHELF_STEP_RUNTIME": "kata"}).rules
    await check_runtime(FakeEngine(runtimes=["runc", "kata"]), rules)
    with pytest.raises(RunnerSettingsError, match="kata") as failed:
        await check_runtime(FakeEngine(runtimes=["runc"]), rules)
    assert "runc" in str(failed.value)


async def test_an_engine_is_not_asked_for_runtimes_when_docker_is_off() -> None:
    await check_runtime(FakeEngine(runtimes=[]), read_settings(GOOD).rules)


def test_the_profile_is_standard_unless_the_operator_names_another() -> None:
    on = {**GOOD, "SHELF_STEP_DOCKER": "on", "SHELF_STEP_RUNTIME": "kata"}
    assert read_settings(on).rules.docker_profile == "standard"
    assert read_settings({**on, "SHELF_STEP_DOCKER_PROFILE": "unconfined"}).rules.docker_profile == "unconfined"


@pytest.mark.parametrize("value", ["privileged", "all", "Standard ", "none"])
def test_a_profile_that_does_not_exist_is_refused_by_name_with_the_accepted_ones(value: str) -> None:
    on = {**GOOD, "SHELF_STEP_DOCKER": "on", "SHELF_STEP_RUNTIME": "kata", "SHELF_STEP_DOCKER_PROFILE": value}
    with pytest.raises(RunnerSettingsError, match="SHELF_STEP_DOCKER_PROFILE") as failed:
        read_settings(on)
    assert "standard" in str(failed.value)
    assert "systempaths" in str(failed.value)
    assert "full" in str(failed.value)
