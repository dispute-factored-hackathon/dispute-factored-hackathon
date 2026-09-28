import tempfile
import unittest
from pathlib import Path

from dispute_agent.authentication import (
    AuthenticationAgent,
    AuthStatus,
    CustomerDirectory,
    normalize_name,
)

FIXTURE = Path(__file__).parent / "fixtures" / "customers.csv"


class AuthenticationPolicyTests(unittest.TestCase):
    def test_initial_question_explains_demo_and_requests_full_name(self):
        result = AuthenticationAgent(FIXTURE, language="pt").start()
        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertIn("nome completo", result.message)

    def test_normalization_ignores_case_accents_and_spacing(self):
        self.assertEqual(normalize_name("  JOSÉ   María "), "jose maria")

    def test_directory_lookup_is_accent_insensitive(self):
        matches = CustomerDirectory(FIXTURE).find_by_full_name("jose maria perez lopez")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].full_name, "José María Pérez López")

    def test_duplicate_name_returns_multiple_records(self):
        matches = CustomerDirectory(FIXTURE).find_by_full_name("Alex Santos")
        self.assertEqual(len(matches), 2)

    def test_inactive_customer_is_not_searchable_by_name(self):
        matches = CustomerDirectory(FIXTURE).find_by_full_name("Inactive Person")
        self.assertEqual(matches, [])

    def test_missing_columns_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "customers.csv"
            path.write_text("customer_id,first_name\n1,Ana\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                CustomerDirectory(path)

    def test_silence_preserves_pending_confirmation(self):
        policy = AuthenticationAgent(FIXTURE, language="pt")
        policy._match_claimed_name("Ana Silva")
        result = policy.handle_empty_answer()
        self.assertEqual(result.status, AuthStatus.NEEDS_CONFIRMATION)
        self.assertIsNotNone(policy.pending_customer)

    def test_repeated_silence_hands_off_with_context(self):
        policy = AuthenticationAgent(FIXTURE, language="pt", max_no_response_attempts=2)
        policy.handle_empty_answer()
        result = policy.handle_empty_answer()
        self.assertEqual(result.status, AuthStatus.HUMAN_HANDOFF)
        self.assertEqual(result.handoff_summary["reason"], "repeated_no_response")


if __name__ == "__main__":
    unittest.main()
