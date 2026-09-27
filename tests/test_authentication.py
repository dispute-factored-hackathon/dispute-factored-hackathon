from pathlib import Path
import unittest

from dispute_agent.authentication import AuthenticationAgent, AuthStatus, normalize_name


FIXTURE = Path(__file__).parent / "fixtures" / "customers.csv"


class AuthenticationAgentTests(unittest.TestCase):
    def test_initial_question_asks_for_full_name(self):
        result = AuthenticationAgent(FIXTURE).start()
        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertEqual(result.message, "What is your full name?")

    def test_unique_full_name_authenticates(self):
        result = AuthenticationAgent(FIXTURE).handle_answer("Ana Silva")
        self.assertTrue(result.authenticated)
        self.assertEqual(result.customer.customer_id, "CLI-002")
        self.assertEqual(result.assurance_level, "DEMO_ONLY_NAME_MATCH")

    def test_matching_ignores_case_accents_and_extra_spaces(self):
        result = AuthenticationAgent(FIXTURE).handle_answer("  JOSE   MARIA PEREZ LOPEZ ")
        self.assertTrue(result.authenticated)
        self.assertEqual(result.customer.customer_id, "CLI-001")

    def test_unknown_name_is_not_authenticated(self):
        result = AuthenticationAgent(FIXTURE).handle_answer("Person Who Does Not Exist")
        self.assertEqual(result.status, AuthStatus.NOT_FOUND)
        self.assertFalse(result.authenticated)

    def test_second_unknown_name_routes_to_human(self):
        agent = AuthenticationAgent(FIXTURE)
        agent.handle_answer("Unknown One")
        result = agent.handle_answer("Unknown Two")
        self.assertEqual(result.status, AuthStatus.HUMAN_HANDOFF)

    def test_duplicate_name_is_ambiguous(self):
        result = AuthenticationAgent(FIXTURE).handle_answer("Alex Santos")
        self.assertEqual(result.status, AuthStatus.AMBIGUOUS)
        self.assertFalse(result.authenticated)

    def test_empty_answer_is_treated_as_avoidance(self):
        result = AuthenticationAgent(FIXTURE).handle_answer("")
        self.assertEqual(result.status, AuthStatus.NEEDS_NAME)
        self.assertIn("need your full name", result.message)

    def test_avoidance_is_reprompted_then_handed_off(self):
        agent = AuthenticationAgent(FIXTURE)
        first = agent.handle_answer("Why do you need that?")
        second = agent.handle_answer("I prefer not to say")
        self.assertEqual(first.status, AuthStatus.NEEDS_NAME)
        self.assertEqual(second.status, AuthStatus.HUMAN_HANDOFF)

    def test_normalization_is_deterministic(self):
        self.assertEqual(normalize_name(" José  Muñoz "), "jose munoz")


if __name__ == "__main__":
    unittest.main()
