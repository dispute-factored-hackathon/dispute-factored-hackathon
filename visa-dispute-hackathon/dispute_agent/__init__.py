"""Core components for the call-center dispute agent prototype."""

from .agent_graph import LangGraphAuthenticationAgent
from .authentication import (
    AuthenticationAgent,
    AuthenticationResult,
    AuthStatus,
    Language,
)
from .country_context import CountryContext, country_context, locale_for, opening_prompt
from .intent_classifier import (
    AnswerIntent,
    ConfirmationDecision,
    ConfirmationIntent,
    IntentDecision,
    LocalAvoidanceClassifier,
    LocalConfirmationClassifier,
)
from .language_classifier import LanguageDecision, LocalLanguageClassifier
from .name_extractor import LocalLLMNameExtractor, NameExtractionError
from .openai_interpreter import OpenAITurnInterpreter, TurnAnalysis, TurnIntent

__all__ = [
    "AnswerIntent",
    "AuthStatus",
    "AuthenticationAgent",
    "AuthenticationResult",
    "ConfirmationDecision",
    "ConfirmationIntent",
    "CountryContext",
    "IntentDecision",
    "LangGraphAuthenticationAgent",
    "Language",
    "LanguageDecision",
    "LocalAvoidanceClassifier",
    "LocalConfirmationClassifier",
    "LocalLLMNameExtractor",
    "LocalLanguageClassifier",
    "NameExtractionError",
    "OpenAITurnInterpreter",
    "TurnAnalysis",
    "TurnIntent",
    "country_context",
    "locale_for",
    "opening_prompt",
]
