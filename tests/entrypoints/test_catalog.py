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
