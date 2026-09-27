import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from dispute_agent.gui_app import create_app
from dispute_agent.voice_call import VoiceCallService, VoiceCallStage

FIXTURE = Path(__file__).parent / "fixtures" / "customers.csv"


class VoiceCallServiceTests(unittest.TestCase):
    def setUp(self):
        self.calls = VoiceCallService(FIXTURE)

    def test_known_phone_authenticates_with_customer_language_and_accent(self):
        state = self.calls.start("+55 11 99999-0001")
        self.assertEqual(state.stage, VoiceCallStage.AUTHENTICATED)
        self.assertEqual(state.identity.customer_id, "CLI-002")
        self.assertEqual((state.locale.language, state.locale.accent), ("pt", "brazilian"))
        self.assertEqual(state.locale.source, "customer_record")

    def test_unknown_phone_requires_language_then_document(self):
        state = self.calls.start("+57 300 999 8877")
        self.assertEqual(state.stage, VoiceCallStage.NEEDS_LANGUAGE)
        self.assertEqual((state.locale.language, state.locale.accent), ("es", "colombian"))

        state = self.calls.choose_language(state.call_id, language="es", accent="mexican")
        self.assertEqual(state.stage, VoiceCallStage.NEEDS_DOCUMENT)
        self.assertEqual((state.locale.locale, state.locale.accent), ("es-MX", "mexican"))

        state = self.calls.authenticate_document(state.call_id, "CC123")
        self.assertEqual(state.stage, VoiceCallStage.AUTHENTICATED)
        self.assertEqual(state.identity.customer_id, "CLI-001")
        self.assertEqual((state.locale.locale, state.locale.accent), ("es-MX", "mexican"))

    def test_authenticated_customer_can_change_language_and_accent(self):
        state = self.calls.start("+55 11 99999-0001")
        changed = self.calls.choose_language(state.call_id, language="en", accent="american")
        self.assertEqual(changed.stage, VoiceCallStage.AUTHENTICATED)
        self.assertEqual((changed.locale.language, changed.locale.accent), ("en", "american"))
        self.assertEqual(changed.identity.customer_id, "CLI-002")

    def test_incompatible_accent_is_rejected_without_changing_state(self):
        state = self.calls.start("+55 11 99999-0001")
        with self.assertRaises(ValueError):
            self.calls.choose_language(state.call_id, language="pt", accent="mexican")
        self.assertEqual(self.calls.get(state.call_id), state)


class VoiceCallApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(FIXTURE))

    def test_unknown_phone_api_flow_keeps_selected_preferences(self):
        started = self.client.post(
            "/api/voice/calls", json={"mobile_phone": "+57 300 999 8877"}
        ).json()
        self.assertEqual(started["stage"], "needs_language")
        call_id = started["call_id"]
        selected = self.client.patch(
            f"/api/voice/calls/{call_id}/preferences",
            json={"language": "pt", "accent": "brazilian"},
        ).json()
        self.assertEqual(selected["stage"], "needs_document")
        authenticated = self.client.post(
            f"/api/voice/calls/{call_id}/document", json={"document_number": "CC123"}
        ).json()
        self.assertTrue(authenticated["authenticated"])
        self.assertEqual((authenticated["language"], authenticated["accent"]), ("pt", "brazilian"))


if __name__ == "__main__":
    unittest.main()
