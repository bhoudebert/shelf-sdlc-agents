from shelf.domain.mise_config import NO_CODE_AT_INSTALL
from shelf.domain.model import RepoRef
from shelf.domain.toolchain import (
    DEFAULT_ALLOWED_DOMAINS,
    TOOLCHAIN_NOTE,
    allowed_domains,
    repository_home,
    toolchain_env,
)

REPO = RepoRef("acme", "shop")


def test_every_repository_has_its_own_home_under_the_cache() -> None:
    assert repository_home("/cache", REPO) == "/cache/home/acme__shop"
    assert repository_home("/cache", RepoRef("acme", "other")) != repository_home("/cache", REPO)


def test_a_name_cannot_climb_out_of_the_cache() -> None:
    home = repository_home("/cache", RepoRef("..", "../etc"))
    assert home.startswith("/cache/home/")
    assert "/../" not in home
    assert home.count("/") == 3


def test_the_environment_puts_the_repositorys_tools_in_front_and_trusts_only_its_clone() -> None:
    env = toolchain_env("/cache", REPO, "/work/clone", "/usr/bin:/bin")
    assert env == {
        "HOME": "/cache/home/acme__shop",
        "MISE_YES": "1",
        "MISE_LOCKFILE": "false",
        "MISE_DISABLE_BACKENDS": NO_CODE_AT_INSTALL,
        "MISE_TRUSTED_CONFIG_PATHS": "/work/clone",
        "PATH": "/cache/home/acme__shop/.local/share/mise/shims:/usr/bin:/bin",
    }


def test_without_a_cache_directory_there_is_no_environment() -> None:
    assert toolchain_env("", REPO, "/work/clone", "/usr/bin") == {}


def test_the_operators_domains_are_added_to_the_defaults_without_repeats() -> None:
    domains = allowed_domains(("nexus.example.org", "github.com"))
    assert domains[: len(DEFAULT_ALLOWED_DOMAINS)] == DEFAULT_ALLOWED_DOMAINS
    assert domains.count("github.com") == 1
    assert domains[-1] == "nexus.example.org"


def test_the_note_tells_the_agent_to_install_then_run_the_repositorys_own_tests() -> None:
    assert "mise install" in TOOLCHAIN_NOTE
    assert "run the repository's own build and tests" in TOOLCHAIN_NOTE
    assert "instead of claiming a result you could not check" in " ".join(TOOLCHAIN_NOTE.split())


def test_a_repository_that_declares_no_tools_is_still_told_to_run_what_its_ci_runs_with_the_versions_ci_uses() -> None:
    from shelf.domain.toolchain import TOOLCHAIN_NOTE  # noqa: PLC0415

    assert ".github/workflows/" in TOOLCHAIN_NOTE
    assert "mise exec <tool>@<version> -- <command>" in TOOLCHAIN_NOTE
    assert "never `mise use`" in TOOLCHAIN_NOTE
    assert "which command and why" in TOOLCHAIN_NOTE


def test_the_environment_disables_the_backends_that_run_code_and_writes_no_lockfile() -> None:
    env = toolchain_env("/cache", REPO, "/work/clone", "/usr/bin")
    assert env["MISE_LOCKFILE"] == "false"
    assert set(env["MISE_DISABLE_BACKENDS"].split(",")) >= {"asdf", "vfox", "npm", "cargo", "pipx"}


def test_a_check_runs_with_the_tools_on_its_path_and_a_compound_command_stays_whole() -> None:
    from shelf.domain.toolchain import with_environment  # noqa: PLC0415

    env = toolchain_env("/cache", REPO, "/work/clone", "/usr/bin")
    wrapped = with_environment(env, "./mvnw -B verify && echo done")
    assert wrapped.startswith("env ")
    assert wrapped.endswith("sh -c './mvnw -B verify && echo done'")
    assert with_environment({}, "make test") == "make test"


def test_the_note_about_tools_says_the_system_runs_the_checks_and_that_there_is_no_docker() -> None:
    from shelf.domain.toolchain import SANDBOX_RECIPES, TOOLCHAIN_NOTE  # noqa: PLC0415

    for text in (SANDBOX_RECIPES, TOOLCHAIN_NOTE):
        assert "run by the system after you finish" in text
        assert "Docker is not available" in text


def test_the_sandbox_may_reach_the_hosts_a_jdk_and_maven_come_from() -> None:
    from shelf.domain.toolchain import DEFAULT_ALLOWED_DOMAINS  # noqa: PLC0415

    for host in ("mise-java.jdx.dev", "api.adoptium.net", "cdn.azul.com", "corretto.aws", "archive.apache.org"):
        assert host in DEFAULT_ALLOWED_DOMAINS
