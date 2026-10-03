"""Server-owned policy for transferring a SIP call to human support."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class HandoffAvailability(StrEnum):
    AVAILABLE = "available"
    NOT_CONFIGURED = "not_configured"
    SAME_AS_CALLER = "same_as_caller"


@dataclass(frozen=True)
class HumanHandoffPlan:
    availability: HandoffAvailability
    target_uri: str | None = None

    @property
    def can_transfer(self) -> bool:
        return self.availability is HandoffAvailability.AVAILABLE


def normalize_e164(value: str | None) -> str | None:
    """Return a strict E.164-like number or ``None`` for unusable input."""

    if value is None:
        return None
    digits = re.sub(r"\D", "", value)
    if not 8 <= len(digits) <= 15:
        return None
    return f"+{digits}"


class HumanHandoffPolicy:
    """Resolve one fixed, trusted human destination for a caller."""

    def __init__(self, target_phone: str | None) -> None:
        self.target_phone = normalize_e164(target_phone)

    def plan(self, caller_phone: str) -> HumanHandoffPlan:
        if self.target_phone is None:
            return HumanHandoffPlan(HandoffAvailability.NOT_CONFIGURED)

        if normalize_e164(caller_phone) == self.target_phone:
            return HumanHandoffPlan(HandoffAvailability.SAME_AS_CALLER)

        return HumanHandoffPlan(
            HandoffAvailability.AVAILABLE,
            target_uri=f"tel:{self.target_phone}",
        )
