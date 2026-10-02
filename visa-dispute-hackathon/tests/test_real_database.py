"""Integration checks against the complete synthetic customer database."""

import unittest
from pathlib import Path

from dispute_agent.authentication import CustomerDirectory

REAL_CUSTOMERS = Path(__file__).parents[2] / "data" / "raw" / "customers.csv"


@unittest.skipUnless(REAL_CUSTOMERS.is_file(), "complete synthetic database is not available")
class RealDatabaseIntegrationTests(unittest.TestCase):
    def test_lookup_resolves_accented_customer_without_accents(self):
        matches = CustomerDirectory(REAL_CUSTOMERS).find_by_full_name("samuel andres diaz perez")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].customer_id, "CLI-G4X2AMVD62NR")
        self.assertEqual(matches[0].full_name, "Samuel Andrés Díaz Pérez")


if __name__ == "__main__":
    unittest.main()
