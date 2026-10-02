import unittest
from pathlib import Path

from dispute_agent.voice_call import (
    VoiceAuthenticationMethod,
    VoiceCallService,
    VoiceCallStage,
)

FIXTURE = Path(__file__).parent / "fixtures" / "customers.csv"


class VoiceCallServiceTests(unittest.TestCase):
    def setUp(self):
        self.calls = VoiceCallService(FIXTURE)

    def test_known_phone_starts_with_language_confirmation_not_authentication(self):
        state = self.calls.start(
            "+55 11 99999-0001",
            call_id="call_known",
        )

        self.assertEqual(state.call_id, "call_known")
        self.assertEqual(
            state.stage,
            VoiceCallStage.NEEDS_LANGUAGE_CONFIRMATION,
        )
        self.assertIsNone(state.identity)
        self.assertIsNone(state.authentication_method)
        self.assertEqual(
            (
                state.locale.language,
                state.locale.locale,
                state.locale.accent,
            ),
            ("pt", "pt-BR", "brazilian"),
        )

    def test_confirm_inferred_language_then_phone_authentication_succeeds(self):
        state = self.calls.start(
            "+55 11 99999-0001",
            call_id="call_phone_auth",
        )

        state = self.calls.confirm_language(state.call_id)

        self.assertEqual(
            state.stage,
            VoiceCallStage.NEEDS_AUTH_METHOD,
        )

        state = self.calls.choose_authentication_method(
            state.call_id,
            method="phone",
        )

        self.assertEqual(
            state.stage,
            VoiceCallStage.AUTHENTICATED,
        )
        self.assertEqual(
            state.authentication_method,
            VoiceAuthenticationMethod.PHONE,
        )
        self.assertIsNotNone(state.identity)
        self.assertEqual(
            state.identity.customer_id,
            "CLI-002",
        )

    def test_explicit_language_change_leads_to_auth_method_choice(self):
        state = self.calls.start(
            "+57 300 999 8877",
            call_id="call_language_change",
        )

        self.assertEqual(
            state.stage,
            VoiceCallStage.NEEDS_LANGUAGE_CONFIRMATION,
        )
        self.assertEqual(state.locale.locale, "es-CO")

        state = self.calls.choose_language(
            state.call_id,
            language="en",
            accent="american",
        )

        self.assertEqual(
            state.stage,
            VoiceCallStage.NEEDS_AUTH_METHOD,
        )
        self.assertEqual(
            (
                state.locale.language,
                state.locale.locale,
                state.locale.accent,
            ),
            ("en", "en-US", "american"),
        )

    def test_unknown_phone_authentication_falls_back_to_document(self):
        state = self.calls.start(
            "+57 300 999 8877",
            call_id="call_phone_fallback",
        )
        state = self.calls.confirm_language(state.call_id)

        state = self.calls.choose_authentication_method(
            state.call_id,
            method="phone",
        )

        self.assertEqual(
            state.stage,
            VoiceCallStage.NEEDS_DOCUMENT,
        )
        self.assertEqual(
            state.authentication_method,
            VoiceAuthenticationMethod.DOCUMENT,
        )
        self.assertIsNone(state.identity)

    def test_document_authentication_can_be_selected_directly(self):
        state = self.calls.start(
            "+57 300 999 8877",
            call_id="call_document",
        )
        state = self.calls.confirm_language(state.call_id)

        state = self.calls.choose_authentication_method(
            state.call_id,
            method="document",
        )

        self.assertEqual(
            state.stage,
            VoiceCallStage.NEEDS_DOCUMENT,
        )
        self.assertEqual(
            state.authentication_method,
            VoiceAuthenticationMethod.DOCUMENT,
        )

        for key in "123456789#":
            state, _ = self.calls.receive_dtmf(
                state.call_id,
                key,
            )

        self.assertEqual(
            state.stage,
            VoiceCallStage.AUTHENTICATED,
        )
        self.assertEqual(
            state.authentication_method,
            VoiceAuthenticationMethod.DOCUMENT,
        )
        self.assertEqual(
            state.identity.customer_id,
            "CLI-001",
        )
        self.assertEqual(state.document_digits, "")

    def test_star_clears_document_entry_before_submission(self):
        state = self.calls.start(
            "+57 300 999 8877",
            call_id="call_document_clear",
        )
        state = self.calls.confirm_language(state.call_id)
        state = self.calls.choose_authentication_method(
            state.call_id,
            method="document",
        )

        for key in "999*123456789#":
            state, _ = self.calls.receive_dtmf(state.call_id, key)

        self.assertEqual(state.stage, VoiceCallStage.AUTHENTICATED)
        self.assertEqual(state.identity.customer_id, "CLI-001")
        self.assertEqual(state.document_digits, "")

    def test_authenticated_customer_can_change_language_without_reauthentication(self):
        state = self.calls.start(
            "+55 11 99999-0001",
            call_id="call_authenticated_language_change",
        )
        state = self.calls.confirm_language(state.call_id)
        state = self.calls.choose_authentication_method(
            state.call_id,
            method="phone",
        )

        changed = self.calls.choose_language(
            state.call_id,
            language="en",
            accent="american",
        )

        self.assertEqual(changed.stage, VoiceCallStage.AUTHENTICATED)
        self.assertEqual(changed.identity.customer_id, "CLI-002")
        self.assertEqual(
            (changed.locale.language, changed.locale.accent),
            ("en", "american"),
        )

    def test_incompatible_accent_does_not_change_call_state(self):
        state = self.calls.start(
            "+55 11 99999-0001",
            call_id="call_invalid_accent",
        )

        with self.assertRaises(ValueError):
            self.calls.choose_language(
                state.call_id,
                language="pt",
                accent="mexican",
            )

        self.assertEqual(self.calls.get(state.call_id), state)

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

                self.assertEqual(
                    state.stage,
                    VoiceCallStage.NEEDS_LANGUAGE_CONFIRMATION,
                )
                self.assertIsNone(state.identity)
                self.assertEqual(
                    (
                        state.locale.language,
                        state.locale.locale,
                        state.locale.accent,
                    ),
                    expected_locale,
                )

    def test_three_failed_documents_handoff(self):
        state = self.calls.start(
            "+57 300 999 8877",
            call_id="call_failed_documents",
        )
        state = self.calls.confirm_language(state.call_id)
        state = self.calls.choose_authentication_method(
            state.call_id,
            method="document",
        )

        for _ in range(3):
            for key in "000#":
                state, _ = self.calls.receive_dtmf(
                    state.call_id,
                    key,
                )

        self.assertEqual(
            state.stage,
            VoiceCallStage.HANDOFF,
        )

    def test_dtmf_is_ignored_before_document_stage(self):
        state = self.calls.start(
            "+55 11 99999-0001",
            call_id="call_early_dtmf",
        )

        unchanged, should_respond = self.calls.receive_dtmf(
            state.call_id,
            "1",
        )

        self.assertEqual(unchanged, state)
        self.assertFalse(should_respond)

    def test_invalid_authentication_method_is_rejected(self):
        state = self.calls.start(
            "+55 11 99999-0001",
            call_id="call_invalid_method",
        )
        state = self.calls.confirm_language(state.call_id)

        with self.assertRaises(ValueError):
            self.calls.choose_authentication_method(
                state.call_id,
                method="face",
            )

    def test_authentication_method_cannot_be_selected_before_language_confirmation(self):
        state = self.calls.start(
            "+55 11 99999-0001",
            call_id="call_wrong_stage",
        )

        with self.assertRaises(ValueError):
            self.calls.choose_authentication_method(
                state.call_id,
                method="phone",
            )


if __name__ == "__main__":
    unittest.main()
