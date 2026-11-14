import pytest

from shelf.domain.catalog import (
    MARKETPLACE,
    CatalogError,
    Hook,
    Kind,
    Source,
    guard_hooks,
    managed_policy,
    marketplace,
    parse_catalog,
)

SHA = "22f0b463e7a5e579904dd6211a520321035526f7"


def entry(**changes: str) -> str:
    fields = {"name": "superpowers", "git": "https://example.com/a.git", "ref": SHA, "kind": "skills", **changes}
    return "[[source]]\n" + "\n".join(f'{key} = "{value}"' for key, value in fields.items()) + "\n"


def test_a_valid_catalog_keeps_its_sources_in_the_order_written() -> None:
    text = entry(name="b") + entry(name="a", kind="plugin", path="sub/dir")
    first, second = parse_catalog(text).sources
    assert (first.name, first.kind, first.path) == ("b", Kind.SKILLS, "")
    assert (second.name, second.kind, second.path) == ("a", Kind.PLUGIN, "sub/dir")


def test_an_empty_catalog_has_no_sources() -> None:
    assert parse_catalog("").sources == ()
    assert parse_catalog("").hooks == ()


@pytest.mark.parametrize("ref", ["main", "v1.2.0", SHA[:7], SHA.upper(), ""])
def test_a_source_must_name_a_full_commit(ref: str) -> None:
    with pytest.raises(CatalogError, match=r"superpowers.*full 40-character commit"):
        parse_catalog(entry(ref=ref))


@pytest.mark.parametrize("path", ["../elsewhere", "a/../../b", "/etc"])
def test_a_path_may_not_leave_the_repository(path: str) -> None:
    with pytest.raises(CatalogError, match=r"superpowers.*inside the repository"):
        parse_catalog(entry(path=path))


def test_the_name_kind_and_keys_are_checked() -> None:
    with pytest.raises(CatalogError, match="lower-case"):
        parse_catalog(entry(name="Bad Name"))
    with pytest.raises(CatalogError, match="kind must be one of"):
        parse_catalog(entry(kind="binary"))
    with pytest.raises(CatalogError, match="unknown keys build"):
        parse_catalog(entry(build="make"))
    with pytest.raises(CatalogError, match="another source has this name"):
        parse_catalog(entry() + entry())


def test_a_source_needs_a_repository_and_a_list_of_skill_folders() -> None:
    with pytest.raises(CatalogError, match="git is required"):
        parse_catalog(entry(git=""))
    with pytest.raises(CatalogError, match="skills must be a list"):
        parse_catalog(entry() + 'skills = "one"\n')
    assert parse_catalog(entry() + 'skills = ["a", "b"]\n').sources[0].skills == ("a", "b")


def test_text_that_is_not_toml_or_has_stray_keys_is_refused() -> None:
    with pytest.raises(CatalogError, match="not valid TOML"):
        parse_catalog("[[source")
    with pytest.raises(CatalogError, match="unknown keys sources"):
        parse_catalog("[[sources]]\n")


def plugin(name: str) -> Source:
    return Source(name, "https://example.com/p.git", SHA, Kind.PLUGIN)


def test_plugins_are_listed_in_the_marketplace_and_enabled_by_the_policy() -> None:
    plugins = [plugin("caveman"), plugin("ponytail")]
    assert [p["name"] for p in marketplace(plugins)["plugins"]] == ["caveman", "ponytail"]
    policy = managed_policy(plugins, [], "/opt/shelf/catalog")
    assert policy["allowManagedHooksOnly"] is True
    assert policy["enabledPlugins"] == {f"caveman@{MARKETPLACE}": True, f"ponytail@{MARKETPLACE}": True}
    assert policy["extraKnownMarketplaces"][MARKETPLACE]["source"] == {
        "source": "directory",
        "path": "/opt/shelf/catalog",
    }


def test_without_plugins_the_policy_still_allows_managed_hooks_only() -> None:
    assert managed_policy([], [], "/opt/shelf/catalog") == {"allowManagedHooksOnly": True}


def test_hooks_are_read_in_the_order_written() -> None:
    text = (
        '[[hook]]\nevent = "PreToolUse"\nmatcher = "Bash"\ncommand = "rtk hook claude"\n\n'
        '[[hook]]\nevent = "SessionStart"\ncommand = "echo hi"\n'
    )
    assert parse_catalog(text).hooks == (Hook("PreToolUse", "rtk hook claude", "Bash"), Hook("SessionStart", "echo hi"))


@pytest.mark.parametrize(
    "entry",
    ['event = "Stop"', 'command = "x"', 'event = "Stop"\ncommand = 1', 'event = "Stop"\ncommand = "x"\nrun = "y"'],
)
def test_a_hook_needs_an_event_and_a_command_and_nothing_else(entry: str) -> None:
    with pytest.raises(CatalogError, match="hook 1"):
        parse_catalog(f"[[hook]]\n{entry}\n")


def test_operator_hooks_go_in_the_policy_grouped_by_event_with_their_matcher() -> None:
    hooks = [Hook("PreToolUse", "rtk hook claude", "Bash"), Hook("PreToolUse", "audit"), Hook("Stop", "bye")]
    policy = managed_policy([], hooks, "/opt/shelf/catalog")
    assert policy["allowManagedHooksOnly"] is True
    assert policy["hooks"] == {
        "PreToolUse": [
            {"hooks": [{"type": "command", "command": "rtk hook claude"}], "matcher": "Bash"},
            {"hooks": [{"type": "command", "command": "audit"}]},
        ],
        "Stop": [{"hooks": [{"type": "command", "command": "bye"}]}],
    }


def test_wardens_hooks_are_five_blocking_commands_with_a_matcher_on_the_tool_events() -> None:
    hooks = guard_hooks("/usr/local/bin/warden")
    assert [hook.event for hook in hooks] == ["PreToolUse", "PostToolUse", "UserPromptSubmit", "SessionStart", "Stop"]
    assert hooks[0].command == "/usr/local/bin/warden hook claude PreToolUse"
    assert [hook.matcher for hook in hooks] == ["*", "*", "", "", ""]
    assert all(hook.timeout == 20 and hook.on_failure == "block" for hook in hooks)


def test_the_managed_policy_carries_the_timeout_and_the_failure_rule_of_a_hook() -> None:
    policy = managed_policy([], guard_hooks("/w"), "/opt/shelf/catalog")
    entry = policy["hooks"]["PreToolUse"][0]
    assert entry["matcher"] == "*"
    assert entry["hooks"] == [
        {"type": "command", "command": "/w hook claude PreToolUse", "timeout": 20, "onFailure": "block"}
    ]
    assert "matcher" not in policy["hooks"]["Stop"][0]
    assert policy["allowManagedHooksOnly"] is True


def test_the_operators_own_hooks_do_not_gain_a_timeout_or_a_failure_rule() -> None:
    policy = managed_policy([], [Hook("PreToolUse", "rtk hook claude", "Bash")], "/opt/shelf/catalog")
    assert policy["hooks"]["PreToolUse"][0]["hooks"] == [{"type": "command", "command": "rtk hook claude"}]
