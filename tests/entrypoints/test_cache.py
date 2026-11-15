import os
import time
from pathlib import Path

import pytest

from shelf.entrypoints.cache import MARKER, main, prune

DAY = 86400.0


def home(cache: Path, name: str, days_ago: float, *, marker: bool = True) -> Path:
    path = cache / "home" / name
    (path / ".local").mkdir(parents=True)
    (path / ".local" / "tool").write_text("x" * 1000)
    stamp = time.time() - days_ago * DAY
    target = path / MARKER if marker else path
    if marker:
        target.touch()
    os.utime(target, (stamp, stamp))
    return path


def test_a_home_nothing_used_for_forty_days_goes_and_a_recent_one_stays(tmp_path: Path) -> None:
    old, recent = home(tmp_path, "acme__old", 40), home(tmp_path, "acme__recent", 1)
    gone = prune(tmp_path, 30, time.time())
    assert [path.name for path, _ in gone] == ["acme__old"]
    assert gone[0][1] == 1000
    assert not old.exists()
    assert recent.exists()


def test_a_dry_run_says_what_would_go_and_removes_nothing(tmp_path: Path) -> None:
    old = home(tmp_path, "acme__old", 90)
    assert len(prune(tmp_path, 30, time.time(), dry_run=True)) == 1
    assert old.exists()


def test_a_home_without_a_marker_is_judged_by_the_folder_itself(tmp_path: Path) -> None:
    home(tmp_path, "acme__plain", 60, marker=False)
    assert len(prune(tmp_path, 30, time.time())) == 1


def test_nothing_outside_the_homes_folder_is_touched_and_a_link_is_never_followed(tmp_path: Path) -> None:
    other = tmp_path / "keep"
    other.mkdir()
    (other / "file").write_text("x")
    os.utime(other, (0, 0))
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / "link").symlink_to(other)
    assert prune(tmp_path, 1, time.time()) == []
    assert (other / "file").exists()


def test_a_cache_with_no_homes_has_nothing_to_prune(tmp_path: Path) -> None:
    assert prune(tmp_path, 30, time.time()) == []


def test_the_command_prunes_the_folder_the_environment_names_and_says_what_it_did(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home(tmp_path, "acme__old", 40)
    monkeypatch.setenv("SHELF_CACHE_DIR", str(tmp_path))
    assert main(["prune", "--older-than", "30"]) == 0
    out = capsys.readouterr().out
    assert "removed acme__old" in out
    assert "removed 1 homes" in out


def test_without_a_cache_directory_the_command_says_so_and_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SHELF_CACHE_DIR", raising=False)
    assert main(["prune"]) == 1
    assert "SHELF_CACHE_DIR is not set" in capsys.readouterr().err
