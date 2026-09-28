import unittest
from pathlib import Path

from dispute_agent.voice_call import VoiceCallService, VoiceCallStage

FIXTURE = Path(__file__).parent / "fixtures" / "customers.csv"


class VoiceCallServiceTests(unittest.TestCase):
    def setUp(self):
        self.calls = VoiceCallService(FIXTURE)

    def test_known_phone_authenticates_with_customer_locale(self):
        state = self.calls.start("+55 11 99999-0001", call_id="call_known")

        self.assertEqual(state.call_id, "call_known")
        self.assertEqual(state.stage, VoiceCallStage.AUTHENTICATED)
        self.assertEqual(state.identity.customer_id, "CLI-002")
        self.assertEqual((state.locale.language, state.locale.accent), ("pt", "brazilian"))

    def test_unknown_phone_uses_language_and_keypad_document(self):
        state = self.calls.start("+57 300 999 8877", call_id="call_unknown")
        self.assertEqual(state.stage, VoiceCallStage.NEEDS_LANGUAGE)
        self.assertEqual(state.locale.locale, "es-CO")

        state = self.calls.choose_language(state.call_id, language="es", accent="mexican")
        self.assertEqual(state.stage, VoiceCallStage.NEEDS_DOCUMENT)
        for key in "123456789#":
            state, _ = self.calls.receive_dtmf(state.call_id, key)

        self.assertEqual(state.stage, VoiceCallStage.AUTHENTICATED)
        self.assertEqual(state.identity.customer_id, "CLI-001")
        self.assertEqual(state.document_digits, "")

    def test_unknown_number_uses_calling_code_only_as_regional_hint(self):
        scenarios = {
            "+525599998877": ("es", "es-MX", "mexican"),
            "+5491199998877": ("es", "es-AR", "argentinian"),
            "+551199998877": ("pt", "pt-BR", "brazilian"),
            "+14155550123": ("en", "en-US", "american"),
        }

        for phone, expected_locale in scenarios.items():
            with self.subTest(phone=phone):
                state = self.calls.start(phone)
                self.assertEqual(state.stage, VoiceCallStage.NEEDS_LANGUAGE)
                self.assertEqual(
                    (state.locale.language, state.locale.locale, state.locale.accent),
                    expected_locale,
                )

    def test_three_failed_documents_handoff(self):
        state = self.calls.start("+57 300 999 8877")
        state = self.calls.choose_language(state.call_id, language="es")
        for _ in range(3):
            for key in "000#":
                state, _ = self.calls.receive_dtmf(state.call_id, key)
        self.assertEqual(state.stage, VoiceCallStage.HANDOFF)

    def test_dtmf_is_ignored_outside_document_stage(self):
        state = self.calls.start("+55 11 99999-0001")
        unchanged, should_respond = self.calls.receive_dtmf(state.call_id, "1")
        self.assertEqual(unchanged, state)
        self.assertFalse(should_respond)


if __name__ == "__main__":
    unittest.main()
