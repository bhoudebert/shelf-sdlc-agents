import json
import tomllib
from pathlib import Path

import pytest

from shelf.adapters.warden.rules_store import CHANGES_FILE, OVERLAY_FILE, FileGuardRules
from shelf.domain.guard_rules import allow_command, deny_host

AT = "2026-11-15T10:00:00+00:00"


def store(tmp_path: Path) -> FileGuardRules:
    return FileGuardRules(tmp_path / "guard")


@pytest.mark.anyio
async def test_a_rule_that_is_added_is_in_the_overlay_the_guard_reads(tmp_path: Path) -> None:
    rules = store(tmp_path)
    rule = allow_command("gh pr merge 5 --squash", "alice", AT)
    assert rule is not None
    await rules.add(rule)
    parsed = tomllib.loads((tmp_path / "guard" / OVERLAY_FILE).read_text())
    assert parsed["rules"][0]["match"] == "^gh pr merge 5 --squash$"
    assert await rules.rules() == (rule,)


@pytest.mark.anyio
async def test_adding_the_same_rule_twice_changes_nothing(tmp_path: Path) -> None:
    rules = store(tmp_path)
    rule = deny_host("example.org", "alice", AT)
    assert rule is not None
    await rules.add(rule)
    await rules.add(rule)
    assert len(await rules.rules()) == 1
    assert len((tmp_path / "guard" / CHANGES_FILE).read_text().splitlines()) == 1


@pytest.mark.anyio
async def test_every_change_is_logged_with_who_and_when_and_the_log_is_only_added_to(tmp_path: Path) -> None:
    rules = store(tmp_path)
    rule = deny_host("example.org", "alice", AT)
    assert rule is not None
    await rules.add(rule)
    assert await rules.remove(rule.id, "bob", "2026-11-15T11:00:00+00:00")
    log = [json.loads(line) for line in (tmp_path / "guard" / CHANGES_FILE).read_text().splitlines()]
    assert [(entry["change"], entry["by"], entry["subject"]) for entry in log] == [
        ("added", "alice", "example.org"),
        ("removed", "bob", "example.org"),
    ]
    assert await rules.rules() == ()
    assert "deny_domains" not in (tmp_path / "guard" / OVERLAY_FILE).read_text()


@pytest.mark.anyio
async def test_removing_a_rule_that_is_not_there_says_so(tmp_path: Path) -> None:
    assert await store(tmp_path).remove("ui-nothing", "bob", AT) is False


@pytest.mark.anyio
async def test_the_overlay_is_replaced_as_a_whole_and_no_temporary_file_is_left(tmp_path: Path) -> None:
    rules = store(tmp_path)
    for command in ("ls", "pwd", "date"):
        rule = allow_command(command, "alice", AT)
        assert rule is not None
        await rules.add(rule)
    names = sorted(path.name for path in (tmp_path / "guard").iterdir())
    assert names == [CHANGES_FILE, "rules.json", OVERLAY_FILE]


async def test_the_worker_reads_the_sites_the_page_added(tmp_path: Path) -> None:
    from shelf.domain.guard_rules import allow_site  # noqa: PLC0415

    store = FileGuardRules(tmp_path)
    assert store.sites_now() == ()
    rule = allow_site("registry.example.org", "alice", "2026-11-15T10:00:00+00:00")
    assert rule is not None
    await store.add(rule)
    assert store.sites_now() == ("registry.example.org",)
    (tmp_path / "rules.json").write_text("not json")
    assert store.sites_now() == ()
