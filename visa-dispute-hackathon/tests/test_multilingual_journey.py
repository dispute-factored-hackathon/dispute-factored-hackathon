import unittest
from pathlib import Path

from dispute_agent.agent_graph import LangGraphAuthenticationAgent
from dispute_agent.authentication import AuthenticationAgent, AuthStatus
from dispute_agent.language_evaluation import calculate_opening_metrics
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
    def make_agent(self, opening, turns, *, channel="cli"):
        interpreter = OpenAITurnInterpreter(
            opening_model=FakeModel([opening]),
            structured_model=FakeModel(turns),
        )
        policy = AuthenticationAgent(FIXTURE, language="auto", country_code="+57")
        return LangGraphAuthenticationAgent(policy, interpreter, channel=channel)

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

    def test_language_can_be_corrected_during_name_confirmation(self):
        opening = CallOpening(
            country_name="Colombia",
            country_is_ambiguous=False,
            primary_language="es",
            locale="es-CO",
            welcome_message="¿Prefiere español, inglés o portugués?",
        )
        turns = [
            TurnAnalysis(
                language="es",
                intent=TurnIntent.PROVIDES_NAME,
                confidence=1,
                abuse=AbuseClass.BENIGN,
                abuse_confidence=1,
                extracted_name="Ana Silva",
                direct_answer=None,
            ),
            TurnAnalysis(
                language="pt",
                intent=TurnIntent.SELECTS_LANGUAGE,
                confidence=1,
                abuse=AbuseClass.BENIGN,
                abuse_confidence=1,
                extracted_name=None,
                direct_answer=None,
            ),
        ]
        agent = self.make_agent(opening, turns)
        agent.start()
        pending = agent.handle_answer("me llamo Ana Silva")

        corrected = agent.handle_answer("prefiro português")

        self.assertEqual(pending.status, AuthStatus.NEEDS_CONFIRMATION)
        self.assertEqual(corrected.status, AuthStatus.NEEDS_CONFIRMATION)
        self.assertEqual(agent.policy.locale, "pt-BR")
        self.assertIn("nome completo correto", corrected.message)

    def test_voice_and_gui_use_the_same_language_policy(self):
        def journey(channel):
            opening = CallOpening(
                country_name="Mexico",
                country_is_ambiguous=False,
                primary_language="es",
                locale="es-MX",
                welcome_message="¿Prefiere español, inglés o portugués?",
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
            agent = self.make_agent(opening, [choice], channel=channel)
            agent.start()
            result = agent.handle_answer("español")
            return agent.policy.locale, result.status, result.message

        self.assertEqual(journey("voice"), journey("gui"))

    def test_opening_metrics_detect_missing_or_misordered_language_options(self):
        reference = {
            "expected_country": "Brazil",
            "primary_language": "pt",
            "locale": "pt-BR",
            "ambiguous": False,
            "language_order": ["português", "inglês", "espanhol"],
        }
        correct = {
            "country_name": "Brazil",
            "primary_language": "pt",
            "locale": "pt-BR",
            "country_is_ambiguous": False,
            "welcome_message": "Escolha português, inglês ou espanhol.",
            "latency_ms": 100,
        }
        incorrect = {
            **correct,
            "welcome_message": "Escolha inglês ou português.",
            "latency_ms": 300,
        }

        metrics = calculate_opening_metrics([(correct, reference), (incorrect, reference)])

        self.assertEqual(metrics["language_order_accuracy"], 0.5)
        self.assertEqual(metrics["average_latency_ms"], 200)


if __name__ == "__main__":
    unittest.main()
