import pytest

from shelf.entrypoints.runner import RunnerSettingsError, read_settings

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
