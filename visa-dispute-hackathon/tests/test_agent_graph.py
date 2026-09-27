from pathlib import Path
import unittest

from dispute_agent.agent_graph import LangGraphAuthenticationAgent
from dispute_agent.authentication import AuthenticationAgent, AuthStatus
from dispute_agent.openai_interpreter import (
    OpenAIConfirmationClassifier,
    OpenAIIntentClassifier,
    OpenAILanguageClassifier,
    OpenAINameExtractor,
    OpenAITurnInterpreter,
    TurnAnalysis,
    TurnIntent,
)


FIXTURE = Path(__file__).parent / "fixtures" / "customers.csv"


class FakeStructuredModel:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        utterance = messages[-1][1].split("Customer utterance: ", 1)[1]
        return self.responses[utterance]


def make_graph(responses, *, language="pt"):
    model = FakeStructuredModel(responses)
    interpreter = OpenAITurnInterpreter(structured_model=model)
    policy = AuthenticationAgent(
        FIXTURE,
        OpenAIIntentClassifier(interpreter),
        language=language,
        language_classifier=OpenAILanguageClassifier(interpreter),
        name_extractor=OpenAINameExtractor(interpreter),
        country_code="+55",
        confirmation_classifier=OpenAIConfirmationClassifier(interpreter),
    )
    return LangGraphAuthenticationAgent(policy, interpreter), model


class LangGraphAgentTests(unittest.TestCase):
    def test_graph_uses_one_structured_llm_call_per_turn(self):
        name_turn = "meu nome é José María Pérez López"
        graph, model = make_graph({
            name_turn: TurnAnalysis(
                language="pt",
                intent=TurnIntent.PROVIDES_NAME,
                extracted_name="José María Pérez López",
            ),
            "sim": TurnAnalysis(
                language="pt",
                intent=TurnIntent.CONFIRMS,
                extracted_name=None,
            ),
        })

        proposed = graph.handle_answer(name_turn)
        confirmed = graph.handle_answer("sim")

        self.assertEqual(proposed.status, AuthStatus.NEEDS_CONFIRMATION)
        self.assertTrue(confirmed.authenticated)
        self.assertEqual(confirmed.customer.customer_id, "CLI-001")
        self.assertEqual(len(model.calls), 2)

    def test_graph_routes_why_question_to_deterministic_policy_response(self):
        question = "porque precisa dele?"
        graph, model = make_graph({
            question: TurnAnalysis(
                language="pt",
                intent=TurnIntent.ASKS_WHY,
                extracted_name=None,
            ),
        })

        result = graph.handle_answer(question)

        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertIn("perfil sintético", result.message)
        self.assertEqual(len(model.calls), 1)

    def test_different_extracted_name_overrides_misclassified_confirmation(self):
        correction = "não, meu nome é José María Pérez López"
        graph, model = make_graph({
            correction: TurnAnalysis(
                language="pt",
                intent=TurnIntent.CONFIRMS,
                extracted_name="José María Pérez López",
            ),
        })
        # Exact initial lookup needs no LLM; it only creates the confirmation state.
        graph.handle_answer("Ana Silva")

        result = graph.handle_answer(correction)

        self.assertEqual(result.status, AuthStatus.NEEDS_CONFIRMATION)
        self.assertIn("José María Pérez López", result.message)
        self.assertEqual(len(model.calls), 1)

    def test_graph_exposes_three_named_processing_nodes(self):
        graph, _ = make_graph({})
        node_names = set(graph.graph.get_graph().nodes)
        self.assertTrue({"prepare_turn", "apply_policy", "validate_response"} <= node_names)


if __name__ == "__main__":
    unittest.main()
