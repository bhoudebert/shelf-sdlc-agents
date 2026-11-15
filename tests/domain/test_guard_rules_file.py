import tomllib

from shelf.domain.guard_rules import MAX_COMMAND, RuleKind, allow_command, deny_host, is_valid_host, render

AT = "2026-11-15T10:00:00+00:00"


def test_an_allowed_command_becomes_a_rule_that_matches_exactly_it() -> None:
    rule = allow_command("gh pr merge 5 --squash", "alice", AT)
    assert rule is not None
    parsed = tomllib.loads(render((rule,)))
    [entry] = parsed["rules"]
    assert entry["match"] == "^gh pr merge 5 --squash$"
    assert entry["decision"] == "allow"
    assert entry["reason"] == "allowed by alice on 2026-11-15"


def test_a_command_with_regular_expression_characters_is_matched_literally() -> None:
    rule = allow_command("curl https://x.example/a?b=1 && echo 'q'", "alice", AT)
    assert rule is not None
    pattern = tomllib.loads(render((rule,)))["rules"][0]["match"]
    assert "\\?" in pattern
    assert "'" not in pattern


def test_the_hosts_are_one_list_and_the_overlay_is_valid_toml() -> None:
    rules = tuple(
        r
        for r in (
            allow_command("ls", "alice", AT),
            deny_host("Example.ORG", "alice", AT),
            deny_host("webhook.site", "bob", AT),
        )
        if r
    )
    parsed = tomllib.loads(render(rules))
    assert parsed["network"]["deny_domains"] == ["example.org", "webhook.site"]
    assert parsed["version"] == 1


def test_an_overlay_with_no_rules_is_valid_and_empty_of_rules() -> None:
    parsed = tomllib.loads(render(()))
    assert "rules" not in parsed
    assert "network" not in parsed


def test_what_a_policy_file_could_be_fooled_by_is_refused() -> None:
    assert allow_command("", "alice", AT) is None
    assert allow_command("a\nb", "alice", AT) is None
    assert allow_command("x" * (MAX_COMMAND + 1), "alice", AT) is None
    assert allow_command("ls", 'evil"login', AT) is None
    assert deny_host("exa mple.org", "alice", AT) is None
    assert deny_host("example.org/path", "alice", AT) is None
    assert deny_host('x"]\n[paths]', "alice", AT) is None
    assert not is_valid_host("-bad.example")


def test_the_same_rule_always_has_the_same_id() -> None:
    first, second = allow_command("ls", "alice", AT), allow_command("ls", "bob", "later")
    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first.kind is RuleKind.ALLOW_COMMAND
