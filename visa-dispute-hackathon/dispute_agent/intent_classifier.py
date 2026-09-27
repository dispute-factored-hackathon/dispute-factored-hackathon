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


class ConfirmationIntent(StrEnum):
    CONFIRMS = "confirms"
    DENIES = "denies"
    OTHER = "other"


@dataclass(frozen=True)
class ConfirmationDecision:
    intent: ConfirmationIntent
    confidence: float
    probabilities: dict[str, float]


class ConfirmationClassifier(Protocol):
    def classify(self, answer: str) -> ConfirmationDecision: ...


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

    @staticmethod
    def _explicit_intent(answer: str) -> AnswerIntent | None:
        normalized = " ".join(answer.casefold().strip().split())
        phrases = {
            AnswerIntent.REQUESTS_HUMAN: (
                "human", "representative", "agent", "atendente", "falar com uma pessoa",
                "asesor", "hablar con una persona",
            ),
            AnswerIntent.ASKS_WHY: (
                "why", "what for", "why do you need", "why is that needed",
                "por que", "por quê", "porque precisa", "porque precisam",
                "pra que", "para que precisa", "para que precisam",
                "por qué", "porque necesita", "para qué", "para qué necesita",
            ),
            AnswerIntent.AVOIDS_ANSWER: (
                "prefer not", "won't say", "will not say", "não quero informar",
                "prefiro não", "no quiero decir", "prefiero no",
            ),
        }
        for intent, markers in phrases.items():
            if any(marker in normalized for marker in markers):
                return intent
        return None

    def _get_pipeline(self):
        if self._pipeline is None:
            try:
                from transformers import (
                    AutoModelForSequenceClassification,
                    AutoTokenizer,
                    logging as transformers_logging,
                    pipeline,
                )
            except ImportError as exc:
                raise ClassificationError(
                    "Install the local ML dependencies with: uv sync --extra ml"
                ) from exc
            try:
                transformers_logging.set_verbosity_error()
                tokenizer = AutoTokenizer.from_pretrained(self.model_id, local_files_only=True)
                model = AutoModelForSequenceClassification.from_pretrained(
                    self.model_id,
                    local_files_only=True,
                )
                self._pipeline = pipeline(
                    "zero-shot-classification",
                    model=model,
                    tokenizer=tokenizer,
                    device=-1,
                )
            except Exception as exc:
                raise ClassificationError(f"Could not load local model {self.model_id}: {exc}") from exc
        return self._pipeline

    def classify(self, answer: str) -> IntentDecision:
        explicit_intent = self._explicit_intent(answer)
        if explicit_intent is not None:
            probabilities = {intent.value: 0.0025 for intent in AnswerIntent}
            probabilities[explicit_intent.value] = 0.99
            return IntentDecision(explicit_intent, 0.99, probabilities)

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


class LocalConfirmationClassifier:
    """Zero-shot classification of a customer's response to a name confirmation."""

    LABELS = {
        ConfirmationIntent.CONFIRMS: "confirms: yes, sim, sí, correct",
        ConfirmationIntent.DENIES: "denies: no, não, incorrect, wrong",
        ConfirmationIntent.OTHER: "uncertain or unrelated: maybe, talvez, quizás, does not answer",
    }

    def __init__(self, base_classifier: LocalAvoidanceClassifier):
        self.base_classifier = base_classifier

    def classify(self, answer: str) -> ConfirmationDecision:
        candidate_labels = list(self.LABELS.values())
        try:
            output = self.base_classifier._get_pipeline()(
                answer,
                candidate_labels=candidate_labels,
                hypothesis_template="The customer response {}.",
                multi_label=False,
            )
            labels = output["labels"]
            scores = output["scores"]
        except ClassificationError:
            raise
        except Exception as exc:
            raise ClassificationError(f"Local confirmation classification failed: {exc}") from exc
        if not labels or len(labels) != len(scores):
            raise ClassificationError("Local model returned invalid confirmation labels or scores")
        intent_by_label = {label: intent for intent, label in self.LABELS.items()}
        try:
            probabilities = {
                intent_by_label[label].value: float(score)
                for label, score in zip(labels, scores, strict=True)
            }
            top_intent = intent_by_label[labels[0]]
        except (KeyError, TypeError, ValueError) as exc:
            raise ClassificationError("Local model returned an unknown confirmation label") from exc
        return ConfirmationDecision(top_intent, float(scores[0]), probabilities)
