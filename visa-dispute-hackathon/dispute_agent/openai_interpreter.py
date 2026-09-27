"""One structured OpenAI interpretation shared by all policies for a customer turn."""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from .intent_classifier import (
    AnswerIntent,
    ClassificationError,
    ConfirmationDecision,
    ConfirmationIntent,
    IntentDecision,
)
from .language_classifier import LanguageClassificationError, LanguageDecision
from .name_extractor import LocalLLMNameExtractor, NameExtractionError


class TurnIntent(StrEnum):
    PROVIDES_NAME = "provides_name"
    ASKS_WHY = "asks_why"
    AVOIDS_ANSWER = "avoids_answer"
    REQUESTS_HUMAN = "requests_human"
    CONFIRMS = "confirms"
    DENIES = "denies"
    OTHER = "other"


class TurnAnalysis(BaseModel):
    language: Literal["en", "pt", "es", "unknown"]
    intent: TurnIntent
    extracted_name: str | None = Field(
        description="Full name copied from the customer utterance, or null if absent."
    )


class OpenAITurnInterpreter:
    """Use one low-latency structured LLM call per unique utterance and phase."""

    DEFAULT_MODEL = "gpt-4.1-mini"
    SYSTEM_PROMPT = """You interpret one turn in a bank call-center demo.
Return only the requested structured data.

Classify language as en, pt, es, or unknown.
Classify intent as:
- provides_name: states a personal full name
- asks_why: asks why information is needed
- avoids_answer: refuses, avoids, or postpones answering
- requests_human: asks for a human representative
- confirms: confirms the repeated name is correct
- denies: says the repeated name is wrong
- other: anything else

If a full name is present, copy the exact name span into extracted_name. This includes a
corrected name in a denial such as "não, meu nome é Ana Silva". Never invent or repair a
name. Otherwise set extracted_name to null. Interpret short answers such as yes/sim/sí and
no/não using the conversation phase supplied by the application."""

    def __init__(self, *, model: str | None = None, structured_model=None):
        self.model = model or os.getenv("OPENAI_AGENT_MODEL", self.DEFAULT_MODEL)
        self.phase = "name_collection"
        self._structured_model = structured_model
        self._cache: dict[tuple[str, str], TurnAnalysis] = {}

    def set_phase(self, phase: str) -> None:
        self.phase = phase

    def _get_model(self):
        if self._structured_model is None:
            try:
                from langchain_openai import ChatOpenAI

                self._structured_model = ChatOpenAI(
                    model=self.model,
                    temperature=0,
                    max_retries=2,
                ).with_structured_output(TurnAnalysis, method="json_schema")
            except Exception as exc:
                raise ClassificationError(f"Could not initialize OpenAI model: {exc}") from exc
        return self._structured_model

    def analyze(self, text: str) -> TurnAnalysis:
        key = (self.phase, text)
        if key in self._cache:
            return self._cache[key]
        try:
            result = self._get_model().invoke(
                [
                    ("system", self.SYSTEM_PROMPT),
                    ("user", f"Conversation phase: {self.phase}\nCustomer utterance: {text}"),
                ]
            )
            if not isinstance(result, TurnAnalysis):
                result = TurnAnalysis.model_validate(result)
        except ClassificationError:
            raise
        except Exception as exc:
            raise ClassificationError(f"OpenAI turn interpretation failed: {exc}") from exc
        self._cache[key] = result
        return result


class OpenAIIntentClassifier:
    def __init__(self, interpreter: OpenAITurnInterpreter):
        self.interpreter = interpreter

    def classify(self, answer: str) -> IntentDecision:
        analysis = self.interpreter.analyze(answer)
        mapping = {
            TurnIntent.PROVIDES_NAME: AnswerIntent.PROVIDES_NAME,
            TurnIntent.ASKS_WHY: AnswerIntent.ASKS_WHY,
            TurnIntent.AVOIDS_ANSWER: AnswerIntent.AVOIDS_ANSWER,
            TurnIntent.REQUESTS_HUMAN: AnswerIntent.REQUESTS_HUMAN,
        }
        intent = mapping.get(analysis.intent, AnswerIntent.OTHER)
        return IntentDecision(intent, 0.99, {intent.value: 0.99})


class OpenAIConfirmationClassifier:
    def __init__(self, interpreter: OpenAITurnInterpreter):
        self.interpreter = interpreter

    def classify(self, answer: str) -> ConfirmationDecision:
        analysis = self.interpreter.analyze(answer)
        mapping = {
            TurnIntent.CONFIRMS: ConfirmationIntent.CONFIRMS,
            TurnIntent.DENIES: ConfirmationIntent.DENIES,
        }
        intent = mapping.get(analysis.intent, ConfirmationIntent.OTHER)
        probabilities = {candidate.value: 0.005 for candidate in ConfirmationIntent}
        probabilities[intent.value] = 0.99
        return ConfirmationDecision(intent, 0.99, probabilities)


class OpenAINameExtractor:
    def __init__(self, interpreter: OpenAITurnInterpreter):
        self.interpreter = interpreter

    def extract(self, text: str) -> str | None:
        try:
            candidate = self.interpreter.analyze(text).extracted_name
        except ClassificationError as exc:
            raise NameExtractionError(str(exc)) from exc
        if not candidate:
            return None
        return LocalLLMNameExtractor._ground_in_original_text(candidate, text)


class OpenAILanguageClassifier:
    def __init__(self, interpreter: OpenAITurnInterpreter):
        self.interpreter = interpreter

    def classify(self, text: str) -> LanguageDecision:
        try:
            language = self.interpreter.analyze(text).language
        except ClassificationError as exc:
            raise LanguageClassificationError(str(exc)) from exc
        return LanguageDecision(language, 0.99 if language != "unknown" else 0.0)
