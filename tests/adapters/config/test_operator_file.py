import logging
from pathlib import Path

import pytest

from shelf.adapters.config.operator_file import OperatorFile
from shelf.domain.config import InvalidConfigError


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_an_edit_that_adds_a_person_is_seen_without_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "shelf.toml"
    write(path, '[access]\nusers = ["alice"]\n')
    source = OperatorFile(path)
    assert source.current().access.users == frozenset({"alice"})
    write(path, '[access]\nusers = ["alice", "bob"]\n')
    assert source.current().access.users == frozenset({"alice", "bob"})


def test_an_edit_with_a_typo_keeps_the_rules_and_says_so(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "shelf.toml"
    write(path, '[access]\nusers = ["alice"]\n')
    source = OperatorFile(path)
    write(path, "[access]\nusers = [alice]\n")
    with caplog.at_level(logging.ERROR):
        assert source.current().access.users == frozenset({"alice"})
    assert "previous rules stay in force" in caplog.text
    write(path, '[access]\nusers = ["carol"]\n')
    assert source.current().access.users == frozenset({"carol"})


def test_a_deleted_file_keeps_the_rules_until_it_is_back(tmp_path: Path) -> None:
    path = tmp_path / "shelf.toml"
    write(path, '[access]\nusers = ["alice"]\n')
    source = OperatorFile(path)
    path.unlink()
    assert source.current().access.users == frozenset({"alice"})
    write(path, '[access]\nusers = ["dave"]\n')
    assert source.current().access.users == frozenset({"dave"})


def test_an_editor_that_replaces_the_file_is_seen(tmp_path: Path) -> None:
    path = tmp_path / "shelf.toml"
    write(path, '[access]\nusers = ["alice"]\n')
    source = OperatorFile(path)
    replacement = tmp_path / "shelf.toml.swp"
    write(replacement, '[access]\nusers = ["erin"]\n')
    replacement.replace(path)
    assert source.current().access.users == frozenset({"erin"})


def test_the_first_read_is_strict(tmp_path: Path) -> None:
    path = tmp_path / "shelf.toml"
    write(path, "[access]\nusers = [alice]\n")
    with pytest.raises(InvalidConfigError):
        OperatorFile(path)
