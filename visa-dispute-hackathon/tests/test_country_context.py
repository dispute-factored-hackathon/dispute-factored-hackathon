import unittest

from dispute_agent.agent_graph import LangGraphAuthenticationAgent
from dispute_agent.authentication import AuthenticationAgent
from dispute_agent.cli import build_parser
from dispute_agent.country_context import normalize_country_code
from dispute_agent.openai_interpreter import CallOpening, OpenAITurnInterpreter


class FakeOpeningModel:
    def __init__(self, opening):
        self.opening = opening
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return self.opening


class CountryContextTests(unittest.TestCase):
    def test_llm_generates_opening_and_agent_stores_inferred_context(self):
        opening = CallOpening(
            country_name="Brazil",
            country_is_ambiguous=False,
            primary_language="pt",
            locale="pt-BR",
            welcome_message=(
                "Olá! Você ligou para o Bank Factored. Pelo código telefônico, sua ligação "
                "parece vir do Brasil. Deseja continuar em português, inglês ou espanhol?"
            ),
        )
        model = FakeOpeningModel(opening)
        interpreter = OpenAITurnInterpreter(opening_model=model)
        policy = AuthenticationAgent(
            "tests/fixtures/customers.csv", language="auto", country_code="+55"
        )

        result = LangGraphAuthenticationAgent(policy, interpreter).start()

        self.assertEqual(result.message, opening.welcome_message)
        self.assertEqual(policy.inferred_country, "Brazil")
        self.assertEqual(policy.inferred_language, "pt")
        self.assertEqual(policy.inferred_locale, "pt-BR")
        self.assertEqual(model.calls[-1][-1][1], "Telephone country calling code: +55")

    def test_schema_supports_ambiguous_shared_calling_codes(self):
        opening = CallOpening(
            country_name="North American Numbering Plan region",
            country_is_ambiguous=True,
            primary_language="en",
            locale="en-US",
            welcome_message=(
                "Hi! You've reached Bank Factored. Your +1 calling code is shared by several "
                "countries and territories. Continue in English, Spanish, or Portuguese?"
            ),
        )
        self.assertTrue(opening.country_is_ambiguous)
        self.assertNotIn("United States", opening.welcome_message)

    def test_code_normalization_accepts_optional_plus(self):
        self.assertEqual(normalize_country_code("55"), "+55")
        self.assertEqual(normalize_country_code("+55"), "+55")

    def test_cli_accepts_country_code(self):
        args = build_parser().parse_args(["--country-code", "+57"])
        self.assertEqual(args.country_code, "+57")

    def test_cli_requires_country_code_and_has_no_language_override(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([])
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--country-code", "+55", "--language", "pt"])

    def test_invalid_code_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_country_code("Brazil")


if __name__ == "__main__":
    unittest.main()
