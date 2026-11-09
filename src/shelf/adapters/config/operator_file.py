"""The operator's ``shelf.toml``, read again whenever the file changes."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from shelf.adapters.config.toml_files import parse_operator
from shelf.domain.config import InvalidConfigError
from shelf.domain.operator import OperatorConfig

log = logging.getLogger(__name__)

Stamp = tuple[int, int, int]
"""Inode, modification time and size: an editor that replaces the file changes the first, one that edits it in place
changes the others."""


def read_operator(path: Path) -> OperatorConfig:
    """Read ``path``. Without a file nobody can sign in, which is logged loudly; an invalid file is an error."""
    if not path.exists():
        log.warning("%s not found: NOBODY can sign in until it names users, admins or organisations", path)
        return OperatorConfig()
    try:
        return parse_operator(path.read_text(encoding="utf-8"))
    except InvalidConfigError as error:
        message = f'{path} is not valid: {error}. Names go in quotes, e.g. users = ["alice", "bob"]'
        raise InvalidConfigError(message) from error


def _stamp(path: Path) -> Stamp | None:
    try:
        seen = path.stat()
    except OSError:
        return None
    return seen.st_ino, seen.st_mtime_ns, seen.st_size


@dataclass(slots=True)
class OperatorFile:
    """Hands out the operator's configuration and picks up an edit of the file without a restart.

    The first read is strict, so a mistake stops the program at start. A later edit that cannot be read, or that is not
    valid, leaves the rules that were in force and says so in the log: a typo must not lock everybody out, and deleting
    the file does not revoke anyone. Only the access list is meant to change this way; the mode is read at start.
    """

    path: Path
    _config: OperatorConfig = field(init=False)
    _seen: Stamp | None = field(init=False)

    def __post_init__(self) -> None:
        """Read the file once, strictly."""
        self._seen = _stamp(self.path)
        self._config = read_operator(self.path)

    def current(self) -> OperatorConfig:
        """The configuration in force now."""
        stamp = _stamp(self.path)
        if stamp == self._seen:
            return self._config
        self._seen = stamp
        if stamp is None:
            log.warning("%s is gone: keeping the access rules in force until it is back", self.path)
            return self._config
        try:
            self._config = read_operator(self.path)
        except (InvalidConfigError, OSError, UnicodeDecodeError) as error:
            # A line, not a traceback: the message names the file and the mistake.
            log.error("%s changed but cannot be used, so the previous rules stay in force: %s", self.path, error)  # noqa: TRY400
        else:
            log.info("%s changed: access rules reloaded", self.path)
        return self._config
