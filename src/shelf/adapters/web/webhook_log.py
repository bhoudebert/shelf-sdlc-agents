"""What has arrived on the webhook endpoint, kept in memory so an operator can see if GitHub reaches this instance."""

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum, auto

KEPT = 20


class Result(StrEnum):
    """What became of a delivery."""

    APPLIED = auto()
    IGNORED = auto()
    BAD_SIGNATURE = auto()
    REFUSED = auto()


@dataclass(frozen=True, slots=True)
class Delivery:
    """One delivery GitHub made, or tried to make."""

    at: datetime
    event: str
    result: Result
    detail: str = ""


@dataclass(slots=True)
class WebhookLog:
    """The most recent deliveries. Lost on restart, which is fine: it answers "is it arriving now?"."""

    deliveries: deque[Delivery] = field(default_factory=lambda: deque(maxlen=KEPT))

    def record(self, event: str, result: Result, detail: str = "") -> None:
        """Remember a delivery."""
        self.deliveries.append(Delivery(datetime.now(UTC), event, result, detail))

    def last(self) -> Delivery | None:
        """The most recent delivery, if any."""
        return self.deliveries[-1] if self.deliveries else None
