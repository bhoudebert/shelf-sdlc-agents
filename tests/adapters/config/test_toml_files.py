import pytest

from shelf.adapters.config.toml_files import ConfigError, parse_operator, parse_repo_config
from shelf.domain.access import AccessRules
from shelf.domain.config import Role
from shelf.domain.pipeline import EntryPoint
from shelf.domain.policy import DeadlockMode
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


def test_a_repository_may_let_work_go_on_past_a_deadlock_and_by_default_does_not() -> None:
    assert parse_repo_config("[policy]\nproceed_on_deadlock = true").policy.proceed_on_deadlock
    assert not parse_repo_config("").policy.proceed_on_deadlock


def test_a_repository_says_where_its_specs_and_decisions_are_and_what_a_run_writes() -> None:
    config = parse_repo_config(
        '[results]\nspecs = "specs/"\ndecisions = "docs/decisions"\nwrite = ["adr"]\nconflicts = "warn"\n'
    )
    assert config.results.specs == "specs"
    assert config.results.decisions == "docs/decisions"
    assert config.results.write == frozenset({"adr"})
    assert config.results.conflicts.value == "warn"


def test_without_a_results_section_the_standard_places_apply() -> None:
    results = parse_repo_config("").results
    assert (results.specs, results.decisions) == ("openspec/specs", "docs/adr")
    assert results.write == frozenset({"spec", "adr"})
    assert results.conflicts.value == "block"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('[results]\nconflicts = "maybe"', "conflicts must be one of"),
        ('[results]\nwrite = ["code"]', "write may list"),
        ('[results]\nspecs = "/etc"', "specs must be a folder inside the repository"),
        ('[results]\ndecisions = "../outside"', "decisions must be a folder inside the repository"),
        ("[results]\nfolder = 1", "unknown keys: folder"),
    ],
)
def test_a_mistake_in_the_results_section_is_refused_with_a_reason(text: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_repo_config(text)


def test_a_role_with_no_one_in_it_is_refused_because_it_would_lock_its_gate() -> None:
    with pytest.raises(ConfigError, match=r"product_owner has no one: list the people, or leave the role out"):
        parse_repo_config("[roles]\nproduct_owner = []\ntech_lead = ['bob']")


def test_an_empty_roles_section_still_means_anyone_may_decide() -> None:
    assert parse_repo_config("[roles]").roles == {}


def test_the_spec_review_is_quick_and_the_design_review_standard_unless_the_repository_says_otherwise() -> None:
    policy = parse_repo_config("").policy
    assert (policy.spec_review_depth.value, policy.design_review_depth.value) == ("quick", "standard")


def test_the_two_reviews_can_have_different_depths() -> None:
    text = '[policy]\nspec_review_depth = "quick"\ndesign_review_depth = "thorough"'
    policy = parse_repo_config(text).policy
    assert (policy.spec_review_depth.value, policy.design_review_depth.value) == ("quick", "thorough")


def test_a_review_depth_that_is_not_known_is_refused_with_the_choices() -> None:
    with pytest.raises(ConfigError, match="design_review_depth must be one of quick, standard, thorough"):
        parse_repo_config('[policy]\ndesign_review_depth = "deep"')


def test_on_deadlock_names_what_happens_at_a_disagreement() -> None:
    assert parse_repo_config("[policy]\non_deadlock = 'arbitrate-go'").policy.on_deadlock is DeadlockMode.ARBITRATE_GO
    assert parse_repo_config("").policy.on_deadlock is DeadlockMode.ARBITRATE_GO  # the autonomous default
    assert parse_repo_config("[policy]\nproceed_on_deadlock = true").policy.deadlock_mode is DeadlockMode.GO
    with pytest.raises(ConfigError, match="on_deadlock must be one of ask, arbitrate-ask, arbitrate-go, go"):
        parse_repo_config("[policy]\non_deadlock = 'sometimes'")
