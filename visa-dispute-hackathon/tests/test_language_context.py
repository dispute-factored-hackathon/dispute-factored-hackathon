import csv
import tempfile
import unittest
from pathlib import Path

from dispute_agent.gui_session import GuiDemoLoginService
from dispute_agent.language_context import ConversationLocaleContext
from dispute_agent.openai_interpreter import CallOpening

FIXTURE = Path(__file__).parent / "fixtures" / "customers.csv"


class LanguageContextTests(unittest.TestCase):
    def test_gui_session_uses_database_preferences_without_a_model(self):
        service = GuiDemoLoginService(FIXTURE)
        option = service.search("Ana Silva")[0]
        context = service.select(option.selection_token)
        self.assertEqual(context.country, "Brazil")
        self.assertEqual(context.language.language, "pt")
        self.assertEqual(context.language.locale, "pt-BR")
        self.assertEqual(context.language.source, "database")
        self.assertEqual(
            service.language_metrics(),
            {
                "sessions": 1,
                "database_preferences": 1,
                "country_default_fallbacks": 0,
                "product_default_fallbacks": 0,
                "fallback_rate": 0.0,
                "language_detection_model_calls": 0,
            },
        )

    def test_supported_regional_database_preferences(self):
        cases = (
            ("Brazil", "pt", "pt-BR"),
            ("Portugal", "pt", "pt-PT"),
            ("Colombia", "es", "es-CO"),
            ("Mexico", "es", "es-MX"),
            ("Argentina", "es", "es-AR"),
            ("Spain", "es", "es-ES"),
        )
        for country, language, locale in cases:
            with self.subTest(country=country):
                result = ConversationLocaleContext.from_gui_record(
                    country=country,
                    preferred_language=language,
                    locale=locale,
                )
                self.assertEqual((result.language, result.locale), (language, locale))
                self.assertEqual(result.source, "database")

    def test_missing_preferences_use_country_default_with_reason(self):
        result = ConversationLocaleContext.from_gui_record(
            country="México", preferred_language=None, locale=None
        )
        self.assertEqual((result.language, result.locale), ("es", "es-MX"))
        self.assertEqual(result.source, "country_default")
        self.assertEqual(result.fallback_reason, "missing_stored_preferences")

    def test_invalid_preferences_cannot_override_country_default(self):
        result = ConversationLocaleContext.from_gui_record(
            country="Colombia", preferred_language="xx", locale="pt-BR"
        )
        self.assertEqual((result.language, result.locale), ("es", "es-CO"))
        self.assertEqual(result.fallback_reason, "invalid_or_inconsistent_stored_preferences")

    def test_unknown_country_uses_product_default(self):
        result = ConversationLocaleContext.from_gui_record(
            country="Atlantis", preferred_language=None, locale=None
        )
        self.assertEqual((result.language, result.locale), ("en", "en-US"))
        self.assertEqual(result.source, "product_default")

    def test_voice_and_gui_share_the_same_context_contract(self):
        opening = CallOpening(
            country_name="Argentina",
            country_is_ambiguous=False,
            primary_language="es",
            locale="es-AR",
            welcome_message="Hola",
        )
        voice = ConversationLocaleContext.from_voice_opening(opening)
        gui = ConversationLocaleContext.from_gui_record(
            country="Argentina", preferred_language="es", locale="es-AR"
        )
        self.assertEqual((voice.language, voice.locale), (gui.language, gui.locale))
        self.assertNotEqual(voice.source, gui.source)

    def test_gui_values_are_loaded_from_selected_record_not_customer_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "customers.csv"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=[
                        "customer_id",
                        "first_name",
                        "last_name",
                        "customer_status",
                        "country",
                        "preferred_language",
                        "locale",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "customer_id": "SAFE-1",
                        "first_name": "Gui",
                        "last_name": "Customer",
                        "customer_status": "Active",
                        "country": "Colombia",
                        "preferred_language": "es",
                        "locale": "es-CO",
                    }
                )
            service = GuiDemoLoginService(path)
            option = service.search("Gui Customer")[0]
            context = service.select(option.selection_token)
            self.assertEqual(context.language.locale, "es-CO")

    def test_gui_fallback_metrics_are_aggregated_without_customer_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "customers.csv"
            path.write_text(
                "customer_id,first_name,last_name,customer_status,country\n"
                "1,Country,Default,Active,Argentina\n"
                "2,Product,Default,Active,Atlantis\n",
                encoding="utf-8",
            )
            service = GuiDemoLoginService(path)
            for query in ("Country Default", "Product Default"):
                option = service.search(query)[0]
                service.select(option.selection_token)
            metrics = service.language_metrics()
            self.assertEqual(metrics["country_default_fallbacks"], 1)
            self.assertEqual(metrics["product_default_fallbacks"], 1)
            self.assertEqual(metrics["fallback_rate"], 1.0)
            self.assertNotIn("customer_id", metrics)


if __name__ == "__main__":
    unittest.main()
