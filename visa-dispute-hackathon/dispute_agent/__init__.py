"""Core components for the call-center dispute agent prototype."""

from .authentication import AuthenticationAgent, AuthenticationResult, AuthStatus, Language
from .intent_classifier import AnswerIntent, IntentDecision, LocalAvoidanceClassifier
from .language_classifier import LanguageDecision, LocalLanguageClassifier
from .name_extractor import LocalLLMNameExtractor, NameExtractionError
from .country_context import CountryContext, country_context, opening_prompt

__all__ = [
    "AnswerIntent",
    "AuthenticationAgent",
    "AuthenticationResult",
    "AuthStatus",
    "CountryContext",
    "IntentDecision",
    "Language",
    "LanguageDecision",
    "LocalLanguageClassifier",
    "LocalLLMNameExtractor",
    "NameExtractionError",
    "country_context",
    "opening_prompt",
    "LocalAvoidanceClassifier",
]
