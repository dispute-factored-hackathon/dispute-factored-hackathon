import unittest
from pathlib import Path

from dispute_agent.transaction_search import (
    SQLiteTransactionSearchRepository,
    TransactionSearchCriteria,
)
from dispute_agent.voice_call import VoiceCallService, VoiceCallStage
from webapp.backend.services.izzy_agent import IZZY_AGENT_ID, IZZY_EMPLOYEE_CODE

FIXTURE = Path(__file__).parent / "fixtures" / "customers.csv"


class CallInteractionPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.calls = VoiceCallService(FIXTURE, transaction_repository=self.transactions)

    def tearDown(self) -> None:
        self.transactions.close()

    def authenticate(self, call_id: str):
        state = self.calls.start("+55 11 99999-0001", call_id=call_id)
        self.calls.record_transcript_turn(call_id, speaker="agent", text="Olá, eu sou Izzy.")
        self.calls.record_transcript_turn(call_id, speaker="customer", text="Quero português.")
        state = self.calls.confirm_language(call_id)
        return self.calls.choose_authentication_method(state.call_id, method="phone")

    def classify(self, call_id: str):
        self.calls.search_transactions(
            call_id, TransactionSearchCriteria(merchant_query="Lemon Drop Market")
        )
        self.calls.resolve_transaction_candidate(call_id, confirmed=True)
        return self.calls.classify_dispute(
            call_id,
            allegation="UNAUTHORIZED_CARD",
            customer_denies_authorization=True,
        ).state

    def test_authentication_creates_izzy_interaction_and_live_transcript(self):
        state = self.authenticate("call-persist-live")
        service = self.calls.call_interactions

        agent = service.agents.get_by_id(IZZY_AGENT_ID)
        interaction = service.interactions.get_by_id(service.interaction_id(state.call_id))
        transcript = service.transcripts.get_by_interaction(interaction.interaction_id)

        self.assertEqual(agent.employee_code, IZZY_EMPLOYEE_CODE)
        self.assertEqual(agent.agent_type, "Hybrid")
        self.assertEqual(agent.experience_level, "Specialist")
        self.assertEqual(agent.total_monthly_interactions, 1)
        self.assertEqual(interaction.customer_id, "CLI-002")
        self.assertEqual(interaction.channel, "Phone")
        self.assertIn("Customer: Quero português.", transcript.full_text)

        self.calls.record_transcript_turn(
            state.call_id, speaker="customer", text="Foi no Lemon Drop Market."
        )
        updated = service.transcripts.get_by_interaction(interaction.interaction_id)
        self.assertIn("Foi no Lemon Drop Market.", updated.customer_text)

    def test_csat_updates_interaction_survey_and_izzy_average(self):
        state = self.authenticate("call-persist-csat")
        state = self.classify(state.call_id)
        self.assertEqual(state.stage, VoiceCallStage.DISPUTE_CLASSIFIED)

        completed = self.calls.record_csat(state.call_id, rating=4)
        service = self.calls.call_interactions
        interaction = service.interactions.get_by_id(service.interaction_id(state.call_id))
        survey = service.surveys.get_by_interaction(interaction.interaction_id)
        agent = service.agents.get_by_id(IZZY_AGENT_ID)

        self.assertEqual(completed.stage, VoiceCallStage.COMPLETED)
        self.assertEqual(survey.main_score, 4)
        self.assertEqual(survey.comment_sentiment, "Positive")
        self.assertEqual(interaction.sentiment_score, 0.5)
        self.assertEqual(agent.avg_csat, 4.0)
        self.assertTrue(interaction.was_resolved)
        self.assertFalse(interaction.requires_followup)

    def test_csat_must_not_be_guessed_before_classification(self):
        state = self.authenticate("call-persist-invalid-csat")
        with self.assertRaisesRegex(ValueError, "after dispute classification"):
            self.calls.record_csat(state.call_id, rating=5)
        with self.assertRaisesRegex(ValueError, "between 1 and 5"):
            classified = self.classify(state.call_id)
            self.calls.record_csat(classified.call_id, rating=6)


if __name__ == "__main__":
    unittest.main()
