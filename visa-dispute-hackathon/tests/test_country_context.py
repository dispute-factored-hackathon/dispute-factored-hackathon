import unittest

from dispute_agent.country_context import locale_for, normalize_country_code, opening_prompt
from dispute_agent.cli import build_parser


class CountryContextTests(unittest.TestCase):
    def test_mexico_opens_in_spanish_with_requested_language_order(self):
        message = opening_prompt("+52")
        self.assertIn("México", message)
        self.assertTrue(message.startswith("¡Hola!"))
        self.assertIn("Gracias por llamar a Bank Factored", message)
        self.assertIn("español, inglés o portugués", message)

    def test_colombia_opens_in_spanish(self):
        message = opening_prompt("57")
        self.assertIn("Colombia", message)
        self.assertIn("Se ha comunicado con Bank Factored", message)
        self.assertIn("español, inglés o portugués", message)

    def test_argentina_opens_in_spanish(self):
        message = opening_prompt("+54")
        self.assertIn("Argentina", message)
        self.assertIn("Te comunicaste", message)
        self.assertIn("llamás", message)
        self.assertIn("¿Querés", message)
        self.assertIn("español, inglés o portugués", message)

    def test_brazil_opens_in_portuguese_with_requested_language_order(self):
        message = opening_prompt("+55")
        self.assertIn("Brasil", message)
        self.assertTrue(message.startswith("Olá!"))
        self.assertIn("Você ligou para o Bank Factored", message)
        self.assertIn("está ligando do Brasil", message)
        self.assertNotIn("desde o Brasil", message)
        self.assertIn("português, inglês ou espanhol", message)

    def test_portugal_opens_in_portuguese(self):
        message = opening_prompt("351")
        self.assertIn("Portugal", message)
        self.assertIn("está ligando de Portugal", message)
        self.assertIn("português, inglês ou espanhol", message)

    def test_united_states_opens_in_english_with_requested_language_order(self):
        message = opening_prompt("+1")
        self.assertIn("the United States", message)
        self.assertTrue(message.startswith("Hi! You've reached Bank Factored"))
        self.assertIn("English, Spanish, or Portuguese", message)

    def test_other_country_opens_in_english(self):
        message = opening_prompt("+81")
        self.assertIn("Japan", message)
        self.assertIn("We see you're calling from Japan", message)
        self.assertIn("English, Spanish, or Portuguese", message)

    def test_unknown_code_opens_in_english_and_names_code(self):
        message = opening_prompt("+999")
        self.assertIn("country code +999", message)
        self.assertIn("English, Spanish, or Portuguese", message)

    def test_code_normalization_accepts_optional_plus(self):
        self.assertEqual(normalize_country_code("55"), "+55")
        self.assertEqual(normalize_country_code("+55"), "+55")

    def test_cli_accepts_country_code(self):
        args = build_parser().parse_args(["--country-code", "+57"])
        self.assertEqual(args.country_code, "+57")

    def test_invalid_code_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_country_code("Brazil")

    def test_regional_locale_mapping(self):
        self.assertEqual(locale_for("pt", "+55"), "pt-BR")
        self.assertEqual(locale_for("es", "+57"), "es-CO")
        self.assertEqual(locale_for("es", "+52"), "es-MX")
        self.assertEqual(locale_for("es", "+54"), "es-AR")
        self.assertEqual(locale_for("en", "+1"), "en-US")

    def test_language_choice_uses_default_variant_when_country_differs(self):
        self.assertEqual(locale_for("en", "+57"), "en-US")
        self.assertEqual(locale_for("pt", "+52"), "pt-BR")
        self.assertEqual(locale_for("es", "+55"), "es-419")


if __name__ == "__main__":
    unittest.main()
