from shelf.domain.stepenv import jdk_environment

HOME = "/home/step"
ROOT = f"{HOME}/.local/share/mise/installs/java"


def test_the_one_jdk_the_worker_installed_becomes_java_home_and_comes_first_on_the_path() -> None:
    env = jdk_environment({"PATH": "/usr/bin"}, HOME, ["temurin-27.0.1+0"])

    assert env == {"JAVA_HOME": f"{ROOT}/temurin-27.0.1+0", "PATH": f"{ROOT}/temurin-27.0.1+0/bin:/usr/bin"}


def test_a_java_home_that_is_set_is_left_as_it_is() -> None:
    assert jdk_environment({"JAVA_HOME": "/opt/jdk", "PATH": "/usr/bin"}, HOME, ["temurin-27.0.1+0"]) == {}


def test_an_empty_java_home_counts_as_not_set() -> None:
    env = jdk_environment({"JAVA_HOME": "", "PATH": "/usr/bin"}, HOME, ["temurin-27.0.1+0"])

    assert env["JAVA_HOME"].endswith("temurin-27.0.1+0")


def test_several_jdks_are_not_guessed_between() -> None:
    assert jdk_environment({"PATH": "/usr/bin"}, HOME, ["temurin-21", "temurin-27.0.1+0"]) == {}


def test_no_jdk_changes_nothing() -> None:
    assert jdk_environment({"PATH": "/usr/bin"}, HOME, []) == {}


def test_a_path_that_is_missing_is_made() -> None:
    assert jdk_environment({}, HOME, ["jdk"])["PATH"] == f"{ROOT}/jdk/bin"


def test_a_name_with_a_slash_or_a_dot_dot_is_never_trusted() -> None:
    assert jdk_environment({}, HOME, ["../x"]) == {}
    assert jdk_environment({}, HOME, ["a/b"]) == {}
