"""Core components for the call-center dispute agent prototype."""

from .authentication import AuthenticationAgent, AuthenticationResult, AuthStatus, Language
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
from .country_context import CountryContext, country_context, locale_for, opening_prompt
from .agent_graph import LangGraphAuthenticationAgent
from .openai_interpreter import OpenAITurnInterpreter, TurnAnalysis, TurnIntent

__all__ = [
    "AnswerIntent",
    "AuthenticationAgent",
    "AuthenticationResult",
    "AuthStatus",
    "CountryContext",
    "ConfirmationDecision",
    "ConfirmationIntent",
    "IntentDecision",
    "Language",
    "LanguageDecision",
    "LangGraphAuthenticationAgent",
    "LocalLanguageClassifier",
    "LocalLLMNameExtractor",
    "NameExtractionError",
    "OpenAITurnInterpreter",
    "country_context",
    "locale_for",
    "opening_prompt",
    "TurnAnalysis",
    "TurnIntent",
    "LocalAvoidanceClassifier",
    "LocalConfirmationClassifier",
]
