import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dispute_agent.gui_session import DemoLoginError, GuiDemoLoginService

FIXTURE = Path(__file__).parent / "fixtures" / "customers.csv"


class Clock:
    def __init__(self):
        self.value = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self):
        return self.value


class GuiDemoLoginTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.service = GuiDemoLoginService(FIXTURE, now=self.clock)

    def test_empty_query_returns_safe_dropdown_options(self):
        options = self.service.search()
        self.assertGreaterEqual(len(options), 3)
        self.assertEqual(options[0].email, "jose.perez@example.com")
        self.assertNotIn("CLI-", repr(options[0]))

    def test_email_search_is_partial_and_case_insensitive(self):
        options = self.service.search("JOSE.PEREZ@")
        self.assertEqual([option.email for option in options], ["jose.perez@example.com"])

    def test_typed_text_does_not_create_a_session(self):
        self.service.search("ana.silva@example.com")
        with self.assertRaises(DemoLoginError):
            self.service.select("Ana Silva")

    def test_explicit_selection_creates_server_side_context(self):
        option = self.service.search("ana.silva@example.com")[0]
        context = self.service.select(option.selection_token)
        resolved = self.service.resolve_session(context.session_id)
        self.assertEqual(resolved.customer_id, "CLI-002")
        self.assertEqual(resolved.assurance_level, "DEMO_GUI_CUSTOMER_SELECTED")
        self.assertEqual(resolved.country, "Brazil")
        self.assertEqual(resolved.language.locale, "pt-BR")

    def test_selection_token_is_single_use(self):
        token = self.service.search("ana.silva@example.com")[0].selection_token
        self.service.select(token)
        with self.assertRaises(DemoLoginError):
            self.service.select(token)

    def test_tampered_selection_and_session_are_rejected(self):
        with self.assertRaises(DemoLoginError):
            self.service.select("tampered")
        with self.assertRaises(DemoLoginError):
            self.service.resolve_session("tampered")

    def test_same_name_users_are_distinguished_by_email(self):
        options = self.service.search("alex.")
        self.assertEqual(len(options), 2)
        self.assertTrue(all(option.disambiguation for option in options))
        self.assertNotEqual(options[0].disambiguation, options[1].disambiguation)

    def test_inactive_customer_is_not_listed(self):
        self.assertEqual(self.service.search("inactive@example.com"), [])

    def test_expired_selection_and_session_are_rejected(self):
        token = self.service.search("ana.silva@example.com")[0].selection_token
        self.clock.value += timedelta(minutes=6)
        with self.assertRaises(DemoLoginError):
            self.service.select(token)

        fresh = self.service.search("ana.silva@example.com")[0]
        context = self.service.select(fresh.selection_token)
        self.clock.value += timedelta(hours=2)
        with self.assertRaises(DemoLoginError):
            self.service.resolve_session(context.session_id)

    def test_logout_revokes_session(self):
        option = self.service.search("ana.silva@example.com")[0]
        context = self.service.select(option.selection_token)
        self.service.logout(context.session_id)
        with self.assertRaises(DemoLoginError):
            self.service.resolve_session(context.session_id)

    def test_query_and_limit_are_bounded(self):
        with self.assertRaises(ValueError):
            self.service.search("x" * 121)
        with self.assertRaises(ValueError):
            self.service.search(limit=51)


if __name__ == "__main__":
    unittest.main()
