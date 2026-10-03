import unittest
from datetime import date
from pathlib import Path

from dispute_agent.transaction_search import (
    SQLiteTransactionSearchRepository,
    TransactionSearchCriteria,
)
from dispute_agent.voice_call import (
    CardSecurityActionStatus,
    ComplaintFilingStatus,
    DisputeClassificationOutcome,
    TransactionSelectionOutcome,
    VoiceAuthenticationMethod,
    VoiceCallService,
    VoiceCallStage,
)
from webapp.backend.demo_card import demo_card_product_id

FIXTURE = Path(__file__).parent / "fixtures" / "customers.csv"


class VoiceCallServiceTests(unittest.TestCase):
    def setUp(self):
        self.transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.calls = VoiceCallService(
            FIXTURE,
            transaction_repository=self.transactions,
            auto_authenticate_known_phone=False,
        )

    def tearDown(self):
        self.transactions.close()

    def authenticate_known_phone(self, call_id: str):
        state = self.calls.start(
            "+55 11 99999-0001",
            call_id=call_id,
        )
        state = self.calls.confirm_language(state.call_id)
        return self.calls.choose_authentication_method(
            state.call_id,
            method="phone",
        )

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

        changed_back = self.calls.choose_language(
            state.call_id,
            language="pt",
        )

        self.assertEqual(changed_back.stage, VoiceCallStage.AUTHENTICATED)
        self.assertEqual(
            (changed_back.locale.locale, changed_back.locale.accent),
            ("pt-BR", "brazilian"),
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
        self.assertEqual(state.handoff_reason, "authentication_attempts_exhausted")

    def test_explicit_human_request_preserves_authenticated_context(self):
        state = self.authenticate_known_phone("call_explicit_human")

        handed_off = self.calls.request_human(state.call_id)

        self.assertEqual(handed_off.stage, VoiceCallStage.HANDOFF)
        self.assertEqual(handed_off.handoff_reason, "customer_requested")
        self.assertEqual(handed_off.identity, state.identity)
        interaction = self.calls.call_interactions.interactions.get_by_id(
            self.calls.call_interactions.interaction_id(state.call_id)
        )
        self.assertTrue(interaction.was_escalated)

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

    def test_transaction_search_requires_authenticated_caller(self):
        state = self.calls.start(
            "+55 11 99999-0001",
            call_id="call_unauthenticated_search",
        )

        with self.assertRaises(ValueError):
            self.calls.search_transactions(
                state.call_id,
                TransactionSearchCriteria(merchant_query="lemon"),
            )

    def test_transaction_is_selected_only_after_explicit_confirmation(self):
        state = self.authenticate_known_phone("call_transaction_confirmation")

        selection = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(approximate_amount=13.0),
        )

        self.assertEqual(selection.outcome, TransactionSelectionOutcome.CANDIDATE)
        self.assertEqual(selection.state.stage, VoiceCallStage.CONFIRM_TRANSACTION)
        self.assertEqual(
            selection.state.current_transaction.merchant_name,
            "Lemon Drop Market",
        )
        self.assertIsNone(selection.state.confirmed_transaction)

        confirmed = self.calls.resolve_transaction_candidate(
            state.call_id,
            confirmed=True,
        )

        self.assertEqual(confirmed.outcome, TransactionSelectionOutcome.CONFIRMED)
        self.assertEqual(
            confirmed.state.stage,
            VoiceCallStage.NEEDS_DISPUTE_CLASSIFICATION,
        )
        self.assertEqual(
            confirmed.state.confirmed_transaction.transaction_id,
            selection.state.current_transaction.transaction_id,
        )

        classified = self.calls.classify_dispute(
            state.call_id,
            allegation="UNAUTHORIZED_CARD",
            customer_denies_authorization=True,
        )

        self.assertEqual(classified.outcome, DisputeClassificationOutcome.CLASSIFIED)
        self.assertEqual(classified.state.stage, VoiceCallStage.DISPUTE_CLASSIFIED)
        self.assertEqual(
            classified.state.dispute_classification.visa_condition_code,
            "10.4",
        )
        self.assertEqual(
            classified.state.card_security_action,
            CardSecurityActionStatus.BLOCKED,
        )
        self.assertEqual(classified.state.secured_card_last_four, "9999")
        self.assertEqual(
            classified.state.complaint_filing_status,
            ComplaintFilingStatus.FILED,
        )
        self.assertIsNotNone(classified.state.complaint_id)
        self.assertEqual(classified.state.complaint_status, "In Review")
        complaint = self.calls.complaints.get_by_id(classified.state.complaint_id)
        self.assertIsNotNone(complaint)
        self.assertEqual(complaint.customer_id, "CLI-002")
        self.assertEqual(complaint.affected_product_id, demo_card_product_id("CLI-002"))
        self.assertEqual(
            complaint.origin_interaction_id,
            self.calls.call_interactions.interaction_id(state.call_id),
        )
        self.assertEqual(complaint.subcategory, "Visa 10.4 · Other Fraud — Card-Absent Environment")
        self.assertEqual(complaint.reception_channel, "Call Center")
        self.assertEqual(complaint.assigned_agent_id, "IZZY")
        self.assertEqual(
            self.calls.products.get_by_id(demo_card_product_id("CLI-002")).product_status,
            "Blocked",
        )

    def test_duplicate_classification_does_not_block_or_suggest_card_action(self):
        state = self.authenticate_known_phone("call_duplicate_no_block")
        self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(merchant_query="lemon"),
        )
        self.calls.resolve_transaction_candidate(state.call_id, confirmed=True)

        classified = self.calls.classify_dispute(
            state.call_id,
            allegation="DUPLICATE_PROCESSING",
            customer_reports_duplicate=True,
        )

        self.assertEqual(classified.outcome, DisputeClassificationOutcome.CLASSIFIED)
        self.assertIsNone(classified.state.card_security_action)
        self.assertIsNone(classified.state.secured_card_last_four)
        self.assertEqual(
            classified.state.complaint_filing_status,
            ComplaintFilingStatus.FILED,
        )
        complaint = self.calls.complaints.get_by_id(classified.state.complaint_id)
        self.assertEqual(complaint.subcategory, "Visa 12.6.1 · Duplicate Processing")
        self.assertEqual(complaint.priority, "Medium")
        self.assertEqual(
            self.calls.products.get_by_id(demo_card_product_id("CLI-002")).product_status,
            "Active",
        )

    def test_insufficient_classification_does_not_block_card(self):
        state = self.authenticate_known_phone("call_insufficient_no_block")
        self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(merchant_query="lemon"),
        )
        self.calls.resolve_transaction_candidate(state.call_id, confirmed=True)

        classified = self.calls.classify_dispute(
            state.call_id,
            allegation="INSUFFICIENT_INFO",
        )

        self.assertEqual(
            classified.outcome,
            DisputeClassificationOutcome.NEEDS_CLARIFICATION,
        )
        self.assertIsNone(classified.state.card_security_action)
        self.assertIsNone(classified.state.complaint_filing_status)
        self.assertIsNone(classified.state.complaint_id)
        self.assertEqual(
            self.calls.products.get_by_id(demo_card_product_id("CLI-002")).product_status,
            "Active",
        )

    def test_fraud_block_is_idempotent_across_calls(self):
        for index, expected_status in enumerate(
            (
                CardSecurityActionStatus.BLOCKED,
                CardSecurityActionStatus.ALREADY_BLOCKED,
            ),
            start=1,
        ):
            state = self.authenticate_known_phone(f"call_fraud_idempotent_{index}")
            self.calls.search_transactions(
                state.call_id,
                TransactionSearchCriteria(merchant_query="lemon"),
            )
            self.calls.resolve_transaction_candidate(state.call_id, confirmed=True)
            classified = self.calls.classify_dispute(
                state.call_id,
                allegation="UNAUTHORIZED_CARD",
                customer_denies_authorization=True,
            )
            self.assertEqual(classified.state.card_security_action, expected_status)

    def test_card_ownership_failure_is_reported_without_false_success(self):
        state = self.authenticate_known_phone("call_wrong_card_owner")
        product_id = demo_card_product_id("CLI-002")
        product = self.calls.products.get_by_id(product_id)
        self.calls.products.update(product.model_copy(update={"customer_id": "OTHER"}))
        self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(merchant_query="lemon"),
        )
        self.calls.resolve_transaction_candidate(state.call_id, confirmed=True)

        classified = self.calls.classify_dispute(
            state.call_id,
            allegation="UNAUTHORIZED_CARD",
            customer_denies_authorization=True,
        )

        self.assertEqual(
            classified.state.card_security_action,
            CardSecurityActionStatus.FAILED,
        )
        self.assertIsNone(classified.state.secured_card_last_four)
        self.assertEqual(
            self.calls.products.get_by_id(product_id).product_status,
            "Active",
        )

    def test_dispute_classification_requires_a_confirmed_transaction(self):
        state = self.authenticate_known_phone("call_classification_wrong_stage")

        with self.assertRaisesRegex(ValueError, "confirmed transaction"):
            self.calls.classify_dispute(
                state.call_id,
                allegation="DUPLICATE_PROCESSING",
                customer_reports_duplicate=True,
            )

    def test_missing_details_request_clarification_and_preserve_context(self):
        state = self.authenticate_known_phone("call_transaction_clarification")

        unclear = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(currency="USD"),
        )

        self.assertEqual(
            unclear.outcome,
            TransactionSelectionOutcome.NEEDS_CLARIFICATION,
        )
        self.assertEqual(unclear.state.stage, VoiceCallStage.NEEDS_TRANSACTION_DETAILS)
        self.assertEqual(unclear.state.transaction_criteria.currency, "USD")

        refined = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(merchant_query="mango"),
        )

        self.assertEqual(refined.outcome, TransactionSelectionOutcome.CANDIDATE)
        self.assertEqual(refined.state.transaction_criteria.currency, "USD")
        self.assertEqual(refined.state.current_transaction.merchant_name, "Mango Gold Store")

    def test_added_details_repeat_retrieval_and_change_the_top_one(self):
        state = self.authenticate_known_phone("call_transaction_rerank")
        broad = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(merchant_query="fruit"),
        )
        refined = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(approximate_amount=13.0),
        )

        self.assertEqual(broad.state.current_transaction.merchant_name, "Mango Gold Store")
        self.assertEqual(refined.state.current_transaction.merchant_name, "Lemon Drop Market")
        self.assertEqual(refined.state.transaction_search_attempts, 2)
        self.assertEqual(refined.state.transaction_criteria.merchant_query, "fruit")

    def test_refining_current_candidate_does_not_consume_an_extra_guess(self):
        state = self.authenticate_known_phone("call_transaction_current_refinement")
        initial = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(approximate_amount=13.0),
        )
        refined = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(city="Buenos Aires"),
        )

        self.assertEqual(initial.state.transaction_guess_attempts, 1)
        self.assertEqual(refined.state.transaction_guess_attempts, 1)
        self.assertEqual(refined.state.current_transaction.merchant_name, "Lemon Drop Market")

    def test_cannot_answer_refinement_moves_to_a_different_missing_detail(self):
        state = self.authenticate_known_phone("call_transaction_unknown_detail")
        self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(approximate_amount=13.0),
        )
        first_question = self.calls.resolve_transaction_candidate(
            state.call_id,
            confirmed=False,
        )
        second_question = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(),
        )

        self.assertEqual(first_question.state.pending_transaction_detail, "merchant")
        self.assertEqual(second_question.state.pending_transaction_detail, "date")
        self.assertEqual(second_question.state.transaction_guess_attempts, 1)
        self.assertIsNone(second_question.state.current_transaction)

    def test_no_match_can_be_corrected_without_losing_the_call(self):
        state = self.authenticate_known_phone("call_transaction_correction")

        missing = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(merchant_query="dragonfruit"),
        )
        corrected = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(merchant_query="papaya"),
        )

        self.assertEqual(missing.outcome, TransactionSelectionOutcome.NO_MATCH)
        self.assertEqual(corrected.outcome, TransactionSelectionOutcome.CANDIDATE)
        self.assertEqual(corrected.state.current_transaction.merchant_name, "Papaya Sunrise Market")

    def test_explicit_correction_can_replace_wrong_prior_details(self):
        state = self.authenticate_known_phone("call_transaction_replace_correction")
        missing = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(merchant_query="dragonfruit"),
        )

        corrected = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(approximate_amount=13),
            replace_existing=True,
        )

        self.assertEqual(missing.outcome, TransactionSelectionOutcome.NO_MATCH)
        self.assertIsNone(corrected.state.transaction_criteria.merchant_query)
        self.assertEqual(corrected.outcome, TransactionSelectionOutcome.CANDIDATE)
        self.assertEqual(corrected.state.current_transaction.merchant_name, "Lemon Drop Market")

    def test_caller_can_edit_remove_and_clear_active_filters(self):
        state = self.authenticate_known_phone("call_transaction_filter_controls")
        initial = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(
                merchant_query="lemon",
                approximate_amount=13,
                currency="USD",
            ),
        )

        edited = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(approximate_amount=14),
        )
        removed = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(),
            remove_filters=("merchant_query",),
        )
        cleared = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(),
            clear_filters=True,
        )

        self.assertEqual(initial.state.transaction_guess_attempts, 1)
        self.assertEqual(edited.state.transaction_criteria.approximate_amount, 14)
        self.assertEqual(edited.state.transaction_guess_attempts, 1)
        self.assertIsNone(removed.state.transaction_criteria.merchant_query)
        self.assertEqual(removed.state.transaction_criteria.currency, "USD")
        self.assertEqual(cleared.outcome, TransactionSelectionOutcome.NEEDS_CLARIFICATION)
        self.assertFalse(cleared.state.transaction_criteria.has_any_filter)
        self.assertEqual(cleared.state.transaction_guess_attempts, 1)

    def test_three_searches_without_matches_end_with_same_human_handoff(self):
        state = self.authenticate_known_phone("call_transaction_three_no_matches")
        outcomes = []

        for merchant in ("dragonfruit", "lychee", "rambutan"):
            selection = self.calls.search_transactions(
                state.call_id,
                TransactionSearchCriteria(merchant_query=merchant),
                replace_existing=True,
            )
            outcomes.append(selection.outcome)

        self.assertEqual(
            outcomes,
            [
                TransactionSelectionOutcome.NO_MATCH,
                TransactionSelectionOutcome.NO_MATCH,
                TransactionSelectionOutcome.EXHAUSTED,
            ],
        )
        self.assertEqual(selection.state.stage, VoiceCallStage.HANDOFF)
        self.assertEqual(selection.state.transaction_no_match_attempts, 3)
        self.assertEqual(selection.state.handoff_reason, "transaction_search_exhausted")

    def test_three_denied_candidates_end_with_unavailable_human_handoff(self):
        state = self.authenticate_known_phone("call_transaction_exhaustion")
        selection = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(merchant_query="fruit"),
        )

        proposed_ids = []
        refinements = ("grapes", "peach")
        for refinement in (*refinements, None):
            proposed_ids.append(selection.state.current_transaction.transaction_id)
            selection = self.calls.resolve_transaction_candidate(
                state.call_id,
                confirmed=False,
            )
            if refinement is not None:
                self.assertEqual(
                    selection.outcome,
                    TransactionSelectionOutcome.NEEDS_CLARIFICATION,
                )
                self.assertIsNone(selection.state.current_transaction)
                selection = self.calls.search_transactions(
                    state.call_id,
                    TransactionSearchCriteria(merchant_query=refinement),
                )

        self.assertEqual(len(set(proposed_ids)), 3)
        self.assertEqual(selection.outcome, TransactionSelectionOutcome.EXHAUSTED)
        self.assertEqual(selection.state.stage, VoiceCallStage.HANDOFF)
        self.assertEqual(selection.state.handoff_reason, "transaction_search_exhausted")

    def test_rejected_peach_candidate_is_never_returned_after_refinement(self):
        state = self.authenticate_known_phone("call_rejected_peach")
        peach = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(
                date_from=date(2026, 9, 27),
                date_to=date(2026, 9, 27),
            ),
        )
        rejected_id = peach.state.current_transaction.transaction_id

        denied = self.calls.resolve_transaction_candidate(
            state.call_id,
            confirmed=False,
        )
        refined = self.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(city="Lima"),
        )

        self.assertEqual(peach.state.current_transaction.merchant_name, "Peach Grove Grocer")
        self.assertIn(rejected_id, denied.state.rejected_transaction_ids)
        self.assertNotEqual(
            getattr(refined.state.current_transaction, "transaction_id", None),
            rejected_id,
        )


if __name__ == "__main__":
    unittest.main()
