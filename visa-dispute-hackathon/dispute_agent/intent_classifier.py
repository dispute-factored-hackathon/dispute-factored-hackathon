"""Local multilingual intent classification for the full-name question."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class AnswerIntent(StrEnum):
    PROVIDES_NAME = "provides_name"
    AVOIDS_ANSWER = "avoids_answer"
    ASKS_WHY = "asks_why"
    REQUESTS_HUMAN = "requests_human"
    CANCELS = "cancels"
    RESTARTS = "restarts"
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
        AnswerIntent.CANCELS: "asks to cancel or stop the interaction",
        AnswerIntent.RESTARTS: "asks to restart or start over",
        AnswerIntent.OTHER: "gives another unclear or unrelated response",
    }

    def __init__(self, *, model_id: str | None = None, pipeline_instance: Any | None = None):
        self.model_id = model_id or os.getenv("AVOIDANCE_MODEL_ID", self.DEFAULT_MODEL)
        self._pipeline = pipeline_instance
        self._decision_cache: dict[str, IntentDecision] = {}

    @staticmethod
    def _explicit_intent(answer: str) -> AnswerIntent | None:
        normalized = " ".join(answer.casefold().strip().split())
        if re.search(
            r"\b(i want|i need|please|can i speak|connect me|quero|gostaria|posso falar|"
            r"quiero|quisiera|puedo hablar)\b.*\b(human|representative|agent|atendente|"
            r"pessoa|asesor|persona)\b",
            normalized,
        ) or normalized in {"human", "representative", "atendente", "asesor"}:
            return AnswerIntent.REQUESTS_HUMAN
        if any(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", normalized) for phrase in (
            "why", "what for", "why do you need", "why is that needed", "por que", "por quê",
            "porque precisa", "porque precisam", "pra que", "para que precisa", "para que precisam",
            "por qué", "porque necesita", "para qué", "para qué necesita",
        )):
            return AnswerIntent.ASKS_WHY
        if any(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", normalized) for phrase in (
            "prefer not", "won't say", "will not say", "não quero informar", "prefiro não",
            "no quiero decir", "prefiero no",
        )):
            return AnswerIntent.AVOIDS_ANSWER
        if normalized in {
            "stop", "cancel", "never mind", "parar", "pare", "cancelar", "cancele",
            "desisto", "detener", "cancela",
        } or re.fullmatch(r"(please |por favor |quero |quiero )?(stop|cancel|cancelar|cancele|detener|cancela)( please| por favor)?", normalized):
            return AnswerIntent.CANCELS
        if normalized in {
            "restart", "start over", "começar de novo", "recomeçar", "reiniciar",
            "empezar de nuevo", "comenzar de nuevo",
        } or re.fullmatch(r"(please |por favor |quero |quiero )?(restart|start over|começar de novo|recomeçar|reiniciar|empezar de nuevo|comenzar de nuevo)( please| por favor)?", normalized):
            return AnswerIntent.RESTARTS
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
        cache_key = " ".join(answer.casefold().strip().split())
        if cache_key in self._decision_cache:
            return self._decision_cache[cache_key]
        explicit_intent = self._explicit_intent(answer)
        if explicit_intent is not None:
            probabilities = {intent.value: 0.0025 for intent in AnswerIntent}
            probabilities[explicit_intent.value] = 0.99
            decision = IntentDecision(explicit_intent, 0.99, probabilities)
            self._decision_cache[cache_key] = decision
            return decision

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

        decision = IntentDecision(
            intent=top_intent,
            confidence=float(scores[0]),
            probabilities=probabilities,
        )
        self._decision_cache[cache_key] = decision
        return decision


class LocalConfirmationClassifier:
    """Zero-shot classification of a customer's response to a name confirmation."""

    LABELS = {
        ConfirmationIntent.CONFIRMS: "confirms: yes, sim, sí, correct",
        ConfirmationIntent.DENIES: "denies: no, não, incorrect, wrong",
        ConfirmationIntent.OTHER: "uncertain or unrelated: maybe, talvez, quizás, does not answer",
    }

    def __init__(self, base_classifier: LocalAvoidanceClassifier):
        self.base_classifier = base_classifier
        self._decision_cache: dict[str, ConfirmationDecision] = {}

    def classify(self, answer: str) -> ConfirmationDecision:
        cache_key = " ".join(answer.casefold().strip().split())
        if cache_key in self._decision_cache:
            return self._decision_cache[cache_key]
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
        decision = ConfirmationDecision(top_intent, float(scores[0]), probabilities)
        self._decision_cache[cache_key] = decision
        return decision
