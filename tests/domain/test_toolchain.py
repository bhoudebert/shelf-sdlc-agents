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
    assert "instead of claiming a result you could not check" in TOOLCHAIN_NOTE
