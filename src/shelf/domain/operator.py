"""What the operator of an instance decides, in the file mounted in the container."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from shelf.domain.access import AccessRules
from shelf.domain.polling import Mode


@dataclass(frozen=True, slots=True)
class OperatorConfig:
    """The ``shelf.toml`` of an instance."""

    access: AccessRules = field(default_factory=AccessRules)
    mode: Mode = Mode.LOCAL
    roles: Mapping[str, tuple[str, ...]] = field(default_factory=dict[str, tuple[str, ...]])
    """For each agent role, the catalog skill sources it loads."""
