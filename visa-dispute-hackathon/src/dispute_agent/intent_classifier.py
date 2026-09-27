"""Local multilingual intent classification for the full-name question."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class AnswerIntent(StrEnum):
    PROVIDES_NAME = "provides_name"
    AVOIDS_ANSWER = "avoids_answer"
    ASKS_WHY = "asks_why"
    REQUESTS_HUMAN = "requests_human"
    OTHER = "other"


@dataclass(frozen=True)
class IntentDecision:
    intent: AnswerIntent
    confidence: float
    probabilities: dict[str, float]


class AnswerIntentClassifier(Protocol):
    def classify(self, answer: str) -> IntentDecision: ...


class ClassificationError(RuntimeError):
    """Raised when the local model cannot return a valid classification."""


class LocalAvoidanceClassifier:
    """Multilingual zero-shot classifier backed by a local Hugging Face model."""

    DEFAULT_MODEL = "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli"
    LABELS = {
        AnswerIntent.PROVIDES_NAME: "provides a personal full name",
        AnswerIntent.AVOIDS_ANSWER: "avoids or refuses to provide a name",
        AnswerIntent.ASKS_WHY: "asks why the name is needed",
        AnswerIntent.REQUESTS_HUMAN: "requests a human representative",
        AnswerIntent.OTHER: "gives another unclear or unrelated response",
    }

    def __init__(self, *, model_id: str | None = None, pipeline_instance: Any | None = None):
        self.model_id = model_id or os.getenv("AVOIDANCE_MODEL_ID", self.DEFAULT_MODEL)
        self._pipeline = pipeline_instance

    def _get_pipeline(self):
        if self._pipeline is None:
            try:
                from transformers import pipeline
            except ImportError as exc:
                raise ClassificationError(
                    "Install the local ML dependencies with: uv sync --extra ml"
                ) from exc
            try:
                self._pipeline = pipeline(
                    "zero-shot-classification",
                    model=self.model_id,
                    device=-1,
                )
            except Exception as exc:
                raise ClassificationError(f"Could not load local model {self.model_id}: {exc}") from exc
        return self._pipeline

    def classify(self, answer: str) -> IntentDecision:
        candidate_labels = list(self.LABELS.values())
        try:
            output = self._get_pipeline()(
                answer,
                candidate_labels=candidate_labels,
                hypothesis_template="This response {}.",
                multi_label=False,
            )
            labels = output["labels"]
            scores = output["scores"]
        except ClassificationError:
            raise
        except Exception as exc:
            raise ClassificationError(f"Local intent classification failed: {exc}") from exc

        if not labels or len(labels) != len(scores):
            raise ClassificationError("Local model returned invalid labels or scores")

        intent_by_label = {label: intent for intent, label in self.LABELS.items()}
        try:
            probabilities = {
                intent_by_label[label].value: float(score)
                for label, score in zip(labels, scores, strict=True)
            }
            top_intent = intent_by_label[labels[0]]
        except (KeyError, TypeError, ValueError) as exc:
            raise ClassificationError("Local model returned an unknown intent label") from exc

        return IntentDecision(
            intent=top_intent,
            confidence=float(scores[0]),
            probabilities=probabilities,
        )
