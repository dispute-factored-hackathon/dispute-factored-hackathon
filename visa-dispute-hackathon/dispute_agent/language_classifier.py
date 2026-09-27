"""Legacy policy protocol; runtime language detection is part of the LLM schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LanguageClassificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class LanguageDecision:
    language: str
    confidence: float


class LanguageClassifier(Protocol):
    def classify(self, text: str) -> LanguageDecision: ...
