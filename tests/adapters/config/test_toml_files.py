import pytest

from shelf.adapters.config.toml_files import ConfigError, parse_operator, parse_repo_config
from shelf.domain.access import AccessRules
from shelf.domain.config import Role
from shelf.domain.pipeline import EntryPoint
from shelf.domain.polling import Mode


def test_an_empty_operator_file_names_nobody_and_is_a_local_instance() -> None:
    config = parse_operator("")
    assert not config.access.is_configured
    assert config.mode is Mode.LOCAL


def test_the_operator_file_lists_who_may_sign_in() -> None:
    config = parse_operator(
        """
mode = "server"

[access]
orgs = ["acme"]
users = ["alice"]
admins = ["alice"]
"""
    )
    assert config.mode is Mode.SERVER
    assert config.access == AccessRules(frozenset({"acme"}), frozenset({"alice"}), frozenset({"alice"}))


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("mode = 'cloud'", "mode must be one of"),
        ("[acess]\nusers = []", "unknown keys: acess"),
        ("[access]\nusers = 'alice'", "users must be a list of strings"),
        ("[access\n", "not valid TOML"),
    ],
)
def test_a_bad_operator_file_is_refused_with_a_reason(text: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_operator(text)


def test_a_repository_without_a_file_gets_the_defaults() -> None:
    config = parse_repo_config("")
    assert config.entries == frozenset(EntryPoint)
    assert config.policy.max_rounds == 3
    assert not config.roles


def test_a_repository_file_sets_entries_policy_checks_and_roles() -> None:
    config = parse_repo_config(
        """
entries = ["need", "pull_request_review"]
base_branch = "develop"
checks = ["make test"]

[policy]
max_rounds = 2
design_review = false

[roles]
product_owner = ["alice"]
tech_lead = ["bob", "carol"]
"""
    )
    assert config.entries == frozenset({EntryPoint.NEED, EntryPoint.PULL_REQUEST_REVIEW})
    assert config.base_branch == "develop"
    assert config.checks == ("make test",)
    assert config.policy.max_rounds == 2
    assert not config.policy.design_review
    assert config.roles[Role.TECH_LEAD] == frozenset({"bob", "carol"})


@pytest.mark.parametrize(
    "text",
    ["entries = ['deploy']", "[policy]\nmax_rounds = 0", "[policy]\nrounds = 2", "[roles]\nking = ['x']"],
)
def test_a_bad_repository_file_is_refused(text: str) -> None:
    with pytest.raises(ConfigError):
        parse_repo_config(text)


def test_the_operator_binds_skill_sources_to_roles() -> None:
    config = parse_operator(
        """
[roles.implementer]
use = ["superpowers", "gdpr"]

[roles.code_reviewer]
use = ["gdpr"]
"""
    )
    assert config.roles == {"implementer": ("gdpr", "superpowers"), "code_reviewer": ("gdpr",)}
    assert parse_operator("").roles == {}


def test_a_binding_for_a_role_that_does_not_exist_names_the_roles_that_do() -> None:
    with pytest.raises(ConfigError, match=r"\[roles.gardener\] is not an agent role; the roles are .*implementer"):
        parse_operator('[roles.gardener]\nuse = ["x"]\n')


def test_a_role_table_takes_only_a_use_list() -> None:
    with pytest.raises(ConfigError, match="unknown keys: skills"):
        parse_operator('[roles.implementer]\nskills = ["x"]\n')
    with pytest.raises(ConfigError, match="use must be a list of strings"):
        parse_operator('[roles.implementer]\nuse = "x"\n')
