"""What the operator of an instance decides, in the file mounted in the container."""

from dataclasses import dataclass, field

from shelf.domain.access import AccessRules
from shelf.domain.polling import Mode


@dataclass(frozen=True, slots=True)
class OperatorConfig:
    """The ``shelf.toml`` of an instance."""

    access: AccessRules = field(default_factory=AccessRules)
    mode: Mode = Mode.LOCAL
