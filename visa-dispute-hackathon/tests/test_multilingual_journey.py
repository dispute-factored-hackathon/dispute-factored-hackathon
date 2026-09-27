import unittest
from pathlib import Path

from dispute_agent.agent_graph import LangGraphAuthenticationAgent
from dispute_agent.authentication import AuthenticationAgent, AuthStatus
from dispute_agent.openai_interpreter import (
    AbuseClass,
    CallOpening,
    OpenAITurnInterpreter,
    TurnAnalysis,
    TurnIntent,
)

FIXTURE = Path(__file__).parent / "fixtures" / "customers.csv"


class FakeModel:
    def __init__(self, responses):
        self.responses = iter(responses)

    def invoke(self, messages):
        del messages
        return next(self.responses)


class MultilingualJourneyTests(unittest.TestCase):
    def make_agent(self, opening, turns):
        interpreter = OpenAITurnInterpreter(
            opening_model=FakeModel([opening]),
            structured_model=FakeModel(turns),
        )
        policy = AuthenticationAgent(FIXTURE, language="auto", country_code="+57")
        return LangGraphAuthenticationAgent(policy, interpreter)

    def test_explicit_choice_keeps_inferred_regional_locale(self):
        opening = CallOpening(
            country_name="Colombia",
            country_is_ambiguous=False,
            primary_language="es",
            locale="es-CO",
            welcome_message=(
                "Hola. Por el código telefónico, parece llamar desde Colombia. "
                "¿Prefiere español, inglés o portugués?"
            ),
        )
        choice = TurnAnalysis(
            language="es",
            intent=TurnIntent.SELECTS_LANGUAGE,
            confidence=1,
            abuse=AbuseClass.BENIGN,
            abuse_confidence=1,
            extracted_name=None,
            direct_answer=None,
        )
        agent = self.make_agent(opening, [choice])

        welcome = agent.start()
        result = agent.handle_answer("español")

        self.assertIn("Colombia", welcome.message)
        self.assertEqual(agent.language, "es")
        self.assertEqual(agent.policy.locale, "es-CO")
        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertIn("nombre completo", result.message)

    def test_choice_different_from_inferred_language_uses_safe_default_locale(self):
        opening = CallOpening(
            country_name="Colombia",
            country_is_ambiguous=False,
            primary_language="es",
            locale="es-CO",
            welcome_message="¿Prefiere español, inglés o portugués?",
        )
        choice = TurnAnalysis(
            language="pt",
            intent=TurnIntent.SELECTS_LANGUAGE,
            confidence=1,
            abuse=AbuseClass.BENIGN,
            abuse_confidence=1,
            extracted_name=None,
            direct_answer=None,
        )
        agent = self.make_agent(opening, [choice])

        agent.start()
        result = agent.handle_answer("português")

        self.assertEqual(agent.policy.locale, "pt-BR")
        self.assertIn("nome completo", result.message)

    def test_ambiguous_input_does_not_override_language_choice(self):
        opening = CallOpening(
            country_name="Colombia",
            country_is_ambiguous=False,
            primary_language="es",
            locale="es-CO",
            welcome_message="¿Prefiere español, inglés o portugués?",
        )
        unclear = TurnAnalysis(
            language="unknown",
            intent=TurnIntent.OTHER,
            confidence=0.2,
            abuse=AbuseClass.BENIGN,
            abuse_confidence=1,
            extracted_name=None,
            direct_answer=None,
        )
        agent = self.make_agent(opening, [unclear])

        agent.start()
        result = agent.handle_answer("banana")

        self.assertEqual(agent.language, "auto")
        self.assertIn("English, Portuguese, or Spanish", result.message)


if __name__ == "__main__":
    unittest.main()
