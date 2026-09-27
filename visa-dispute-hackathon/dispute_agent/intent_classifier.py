"""Legacy policy types; runtime classification now uses an LLM JSON schema."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ClassificationError(RuntimeError):
    pass


class AnswerIntent(StrEnum):
    PROVIDES_NAME = "provides_name"
    AVOIDS_ANSWER = "avoids_answer"
    ASKS_WHY = "asks_why"
    REQUESTS_HUMAN = "requests_human"
    CANCELS = "cancels"
    RESTARTS = "restarts"
    OTHER = "other"


class ConfirmationIntent(StrEnum):
    CONFIRMS = "confirms"
    DENIES = "denies"
    OTHER = "other"


@dataclass(frozen=True)
class IntentDecision:
    intent: AnswerIntent
    confidence: float
    probabilities: dict[str, float]


@dataclass(frozen=True)
class ConfirmationDecision:
    intent: ConfirmationIntent
    confidence: float
    probabilities: dict[str, float]


class AnswerIntentClassifier(Protocol):
    def classify(self, answer: str) -> IntentDecision: ...


class ConfirmationClassifier(Protocol):
    def classify(self, answer: str) -> ConfirmationDecision: ...
