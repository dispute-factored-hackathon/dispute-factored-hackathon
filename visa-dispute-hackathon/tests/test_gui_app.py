import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from dispute_agent.gui_app import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "customers.csv"


class GuiAppTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(FIXTURE))

    def test_login_page_contains_accessible_searchable_dropdown(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('role="combobox"', response.text)
        self.assertIn('role="listbox"', response.text)
        self.assertIn("not real bank authentication", response.text)

    def test_search_response_contains_no_customer_id(self):
        response = self.client.get("/api/customers", params={"query": "JOSE.PEREZ@"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["options"][0]["email"], "jose.perez@example.com")
        self.assertNotIn("customer_id", response.text)

    def test_explicit_option_creates_cookie_session_without_exposing_customer_id(self):
        option = self.client.get(
            "/api/customers", params={"query": "ana.silva@example.com"}
        ).json()["options"][0]
        response = self.client.post(
            "/api/session", json={"selection_token": option["selection_token"]}
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.cookies.get("demo_session"))
        self.assertNotIn("customer_id", response.text)
        self.assertEqual(response.json()["language"], "pt")
        self.assertEqual(response.json()["locale"], "pt-BR")
        self.assertEqual(response.json()["language_source"], "database")
        current = self.client.get("/api/session")
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()["display_name"], "Ana Silva")

    def test_typed_email_or_tampered_token_cannot_create_session(self):
        for token in ("ana.silva@example.com", "tampered"):
            with self.subTest(token=token):
                response = self.client.post("/api/session", json={"selection_token": token})
                self.assertEqual(response.status_code, 401)

    def test_logout_revokes_cookie_session(self):
        option = self.client.get(
            "/api/customers", params={"query": "ana.silva@example.com"}
        ).json()["options"][0]
        self.client.post("/api/session", json={"selection_token": option["selection_token"]})
        self.assertEqual(self.client.delete("/api/session").status_code, 204)
        self.assertEqual(self.client.get("/api/session").status_code, 401)


if __name__ == "__main__":
    unittest.main()
