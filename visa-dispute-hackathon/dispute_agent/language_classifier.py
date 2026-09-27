"""Offline statistical language identification for caller utterances."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class LanguageDecision:
    language: str
    confidence: float


class LanguageClassifier(Protocol):
    def classify(self, text: str) -> LanguageDecision: ...


class LanguageClassificationError(RuntimeError):
    """Raised when the local language model cannot classify an utterance."""


class LocalLanguageClassifier:
    """Language identifier backed by langid.py's bundled statistical model."""

    SUPPORTED_LANGUAGES = ("en", "pt", "es")

    def __init__(self, *, identifier_instance: Any | None = None):
        self._identifier = identifier_instance

    def _get_identifier(self):
        if self._identifier is None:
            try:
                from langid.langid import LanguageIdentifier, model
            except ImportError as exc:
                raise LanguageClassificationError(
                    "Install the local ML dependencies with: uv sync --extra ml"
                ) from exc
            try:
                self._identifier = LanguageIdentifier.from_modelstring(
                    model,
                    norm_probs=True,
                )
                self._identifier.set_languages(list(self.SUPPORTED_LANGUAGES))
            except Exception as exc:
                raise LanguageClassificationError(
                    f"Could not initialize the local language model: {exc}"
                ) from exc
        return self._identifier

    def classify(self, text: str) -> LanguageDecision:
        try:
            language, confidence = self._get_identifier().classify(text)
        except LanguageClassificationError:
            raise
        except Exception as exc:
            raise LanguageClassificationError(
                f"Local language classification failed: {exc}"
            ) from exc
        return LanguageDecision(str(language), float(confidence))
