import json
import subprocess
from pathlib import Path

import pytest

from shelf.adapters.catalog.sync import LOCK, POLICY, hook_commands, sync
from shelf.domain.catalog import CatalogError, Kind, Source


def git(directory: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],  # noqa: S607
        cwd=directory,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


def repo(tmp_path: Path, name: str, files: dict[str, str]) -> tuple[str, str]:
    """A git repository with ``files``; returns its URL and its commit."""
    directory = tmp_path / "remotes" / name
    directory.mkdir(parents=True)
    git(directory, "init", "-q", "-b", "main")
    git(directory, "config", "uploadpack.allowAnySHA1InWant", "true")
    for path, content in files.items():
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    git(directory, "add", "-A")
    git(directory, "commit", "-q", "-m", "files")
    return directory.as_uri(), git(directory, "rev-parse", "HEAD")


def skills_repo(tmp_path: Path) -> tuple[str, str]:
    return repo(
        tmp_path,
        "skills",
        {
            "skills/tdd/SKILL.md": "---\nname: tdd\n---\ntdd",
            "skills/tdd/extra.md": "more",
            "skills/debugging/SKILL.md": "---\nname: debugging\n---\nd",
            "hooks/hooks.json": json.dumps({"hooks": {"SessionStart": [{"hooks": [{"command": "evil.sh"}]}]}}),
            ".claude-plugin/plugin.json": json.dumps({"name": "skills", "hooks": ["./hooks/hooks.json"]}),
            "install.sh": "touch INSTALLED\n",
        },
    )


def plugin_repo(tmp_path: Path) -> tuple[str, str]:
    return repo(
        tmp_path,
        "plugin",
        {
            ".claude-plugin/plugin.json": json.dumps(
                {"name": "caveman", "hooks": {"SessionStart": [{"hooks": [{"command": "node a.js"}]}]}}
            ),
            "a.js": "// hook",
            "install.sh": "touch INSTALLED\n",
        },
    )


def outputs(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "out" / "plugins", tmp_path / "out" / "policy"


def source(name: str, location: tuple[str, str], kind: Kind, **changes: object) -> Source:
    return Source(name, location[0], location[1], kind, **changes)  # type: ignore[arg-type]


def test_a_skills_source_becomes_a_plugin_with_only_its_skill_folders_and_no_hook(tmp_path: Path) -> None:
    plugins, policy = outputs(tmp_path)
    sync((source("superpowers", skills_repo(tmp_path), Kind.SKILLS),), plugins, policy, "/opt/shelf/catalog")
    generated = plugins / "superpowers"
    assert sorted(p.name for p in (generated / "skills").iterdir()) == ["debugging", "tdd"]
    assert (generated / "skills" / "tdd" / "extra.md").is_file()
    assert json.loads((generated / ".claude-plugin" / "plugin.json").read_text())["name"] == "superpowers"
    assert not (generated / "hooks").exists()
    assert "hooks" not in json.loads((generated / ".claude-plugin" / "plugin.json").read_text())


def test_a_selection_of_skills_takes_only_those(tmp_path: Path) -> None:
    plugins, policy = outputs(tmp_path)
    sync((source("sp", skills_repo(tmp_path), Kind.SKILLS, skills=("tdd",)),), plugins, policy, "/opt")
    assert [p.name for p in (plugins / "sp" / "skills").iterdir()] == ["tdd"]


def test_a_skill_that_is_not_there_is_named(tmp_path: Path) -> None:
    plugins, policy = outputs(tmp_path)
    with pytest.raises(CatalogError, match=r"sp: no skill named missing \(found: debugging, tdd\)"):
        sync((source("sp", skills_repo(tmp_path), Kind.SKILLS, skills=("missing",)),), plugins, policy, "/opt")


def test_a_plugin_source_is_registered_enabled_and_its_hooks_are_locked(tmp_path: Path) -> None:
    plugins, policy = outputs(tmp_path)
    sync((source("caveman", plugin_repo(tmp_path), Kind.PLUGIN),), plugins, policy, "/opt/shelf/catalog")
    assert (plugins / "caveman" / "a.js").is_file()
    listed = json.loads((plugins / ".claude-plugin" / "marketplace.json").read_text())
    assert [p["name"] for p in listed["plugins"]] == ["caveman"]
    managed = json.loads((policy / POLICY).read_text())
    assert managed["allowManagedHooksOnly"] is True
    assert managed["enabledPlugins"] == {"caveman@shelf-corp": True}
    assert json.loads((plugins / LOCK).read_text())["sources"]["caveman"]["hooks"] == ["node a.js"]


def test_only_skill_sources_enable_no_plugin_and_still_lock_hooks_to_managed(tmp_path: Path) -> None:
    plugins, policy = outputs(tmp_path)
    sync((source("sp", skills_repo(tmp_path), Kind.SKILLS),), plugins, policy, "/opt")
    assert json.loads((policy / POLICY).read_text()) == {"allowManagedHooksOnly": True}


def test_nothing_a_source_contains_is_run(tmp_path: Path) -> None:
    plugins, policy = outputs(tmp_path)
    sync(
        (source("sp", skills_repo(tmp_path), Kind.SKILLS), source("caveman", plugin_repo(tmp_path), Kind.PLUGIN)),
        plugins,
        policy,
        "/opt",
    )
    assert not list(tmp_path.rglob("INSTALLED"))


def test_a_plugin_without_its_manifest_fails_and_leaves_the_catalog_alone(tmp_path: Path) -> None:
    plugins, policy = outputs(tmp_path)
    skills = skills_repo(tmp_path)
    sync((source("sp", skills, Kind.SKILLS),), plugins, policy, "/opt/shelf/catalog")
    before = sorted(str(p.relative_to(plugins)) for p in plugins.rglob("*"))
    bare = repo(tmp_path, "bare", {"README.md": "no plugin here"})
    with pytest.raises(CatalogError, match=r"bare: a plugin needs \.claude-plugin/plugin\.json"):
        sync(
            (source("sp", skills, Kind.SKILLS), source("bare", bare, Kind.PLUGIN)),
            plugins,
            policy,
            "/opt/shelf/catalog",
        )
    assert sorted(str(p.relative_to(plugins)) for p in plugins.rglob("*")) == before


def test_a_skills_source_without_skills_is_refused(tmp_path: Path) -> None:
    plugins, policy = outputs(tmp_path)
    with pytest.raises(CatalogError, match=r"empty: no folder with a SKILL\.md"):
        sync((source("empty", repo(tmp_path, "empty", {"README.md": "x"}), Kind.SKILLS),), plugins, policy, "/opt")


def test_a_commit_the_repository_does_not_have_names_the_source_and_the_commit(tmp_path: Path) -> None:
    plugins, policy = outputs(tmp_path)
    location = skills_repo(tmp_path)
    bogus = Source("ghost", location[0], "0" * 40, Kind.SKILLS)
    with pytest.raises(CatalogError, match=r"ghost: cannot fetch commit 0{40}"):
        sync((bogus,), plugins, policy, "/opt")


def test_a_path_inside_the_repository_roots_the_source(tmp_path: Path) -> None:
    plugins, policy = outputs(tmp_path)
    skills = skills_repo(tmp_path)
    sync((source("only", skills, Kind.SKILLS, path="skills/tdd"),), plugins, policy, "/opt")
    assert [p.name for p in (plugins / "only" / "skills").iterdir()] == ["tdd"]
    with pytest.raises(CatalogError, match="not a folder of the repository"):
        sync((source("nope", skills, Kind.SKILLS, path="absent"),), plugins, policy, "/opt")


def test_hook_commands_are_read_from_the_manifest_and_the_hooks_file_without_running_them(tmp_path: Path) -> None:
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "one"}]}]}})
    )
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"Start": [{"hooks": [{"command": "two"}]}]}}))
    assert hook_commands(tmp_path) == ("one", "two")
    assert hook_commands(tmp_path / "absent") == ()
