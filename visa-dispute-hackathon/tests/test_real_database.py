"""Integration checks against the hackathon's complete synthetic customer database."""

from pathlib import Path
import unittest

from dispute_agent.authentication import AuthenticationAgent
from test_authentication import FakeIntentClassifier, FakeNameExtractor


REAL_CUSTOMERS = Path(__file__).parents[2] / "data" / "raw" / "customers.csv"


@unittest.skipUnless(REAL_CUSTOMERS.is_file(), "complete synthetic database is not available")
class RealDatabaseIntegrationTests(unittest.TestCase):
    def test_natural_response_resolves_a_customer_from_complete_database(self):
        answer = "meu nome é samuel andrés díaz pérez"
        agent = AuthenticationAgent(
            REAL_CUSTOMERS,
            FakeIntentClassifier(),
            language="pt",
            name_extractor=FakeNameExtractor({answer: "samuel andrés díaz pérez"}),
        )

        result = agent.handle_answer(answer)

        self.assertTrue(result.authenticated)
        self.assertEqual(result.customer.customer_id, "CLI-G4X2AMVD62NR")
        self.assertEqual(result.customer.full_name, "Samuel Andrés Díaz Pérez")

    def test_natural_response_without_accents_resolves_accented_database_name(self):
        answer = "meu nome e samuel andres diaz perez"
        agent = AuthenticationAgent(
            REAL_CUSTOMERS,
            FakeIntentClassifier(),
            language="pt",
            name_extractor=FakeNameExtractor({answer: "samuel andres diaz perez"}),
        )

        result = agent.handle_answer(answer)

        self.assertTrue(result.authenticated)
        self.assertEqual(result.customer.customer_id, "CLI-G4X2AMVD62NR")
        self.assertEqual(result.customer.full_name, "Samuel Andrés Díaz Pérez")


if __name__ == "__main__":
    unittest.main()
