import json
from pathlib import Path

import pytest

from shelf.entrypoints.catalog import run


def test_without_a_catalog_file_the_sync_succeeds_with_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run(tmp_path / "absent.toml", tmp_path / "plugins", tmp_path / "policy", "/opt/shelf/catalog")
    assert code == 0
    assert "0 source(s) synced" in capsys.readouterr().out
    assert (tmp_path / "policy" / "managed-settings.json").is_file()


def test_an_invalid_catalog_stops_with_the_reason_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "catalog.toml"
    config.write_text('[[source]]\nname = "a"\ngit = "https://example.com/a.git"\nref = "main"\nkind = "skills"\n')
    code = run(config, tmp_path / "plugins", tmp_path / "policy", "/opt/shelf/catalog")
    assert code == 1
    assert "full 40-character commit" in capsys.readouterr().err
    assert not (tmp_path / "plugins").exists()


def test_warden_comes_first_in_the_managed_policy_ahead_of_the_operators_hooks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "catalog.toml"
    config.write_text('[[hook]]\nevent = "PreToolUse"\nmatcher = "Bash"\ncommand = "rtk hook claude"\n')
    code = run(config, tmp_path / "plugins", tmp_path / "policy", "/opt/shelf/catalog", guard="/usr/local/bin/warden")
    assert code == 0
    policy = json.loads((tmp_path / "policy" / "managed-settings.json").read_text())
    commands = [group["hooks"][0]["command"] for group in policy["hooks"]["PreToolUse"]]
    assert commands == ["/usr/local/bin/warden hook claude PreToolUse", "rtk hook claude"]
    assert set(policy["hooks"]) >= {"UserPromptSubmit", "SessionStart", "Stop", "PostToolUse"}
    out = capsys.readouterr().out
    assert "warden (/usr/local/bin/warden) guards every agent" in out
    assert "operator hook on PreToolUse: rtk hook claude" in out
    assert "operator hook on PreToolUse: /usr/local/bin/warden" not in out


def test_without_a_guard_the_policy_has_only_the_operators_hooks(tmp_path: Path) -> None:
    config = tmp_path / "catalog.toml"
    config.write_text('[[hook]]\nevent = "Stop"\ncommand = "bye"\n')
    assert run(config, tmp_path / "plugins", tmp_path / "policy", "/opt/shelf/catalog") == 0
    policy = json.loads((tmp_path / "policy" / "managed-settings.json").read_text())
    assert list(policy["hooks"]) == ["Stop"]
