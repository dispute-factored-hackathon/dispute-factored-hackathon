import json
import unittest
from datetime import UTC, datetime

from dispute_agent.dispute_classification import (
    CardEnvironment,
    ClassificationStatus,
    DisputeAllegation,
    DisputeClassificationService,
    DisputeEvidence,
    VisaWorkflow,
)
from webapp.backend.models.transaction import Transaction


def transaction(*, channel: str = "Web") -> Transaction:
    timestamp = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    return Transaction(
        transaction_id="SYNTHETIC-TRANSACTION-22",
        transaction_date=timestamp,
        process_date=timestamp.date(),
        product_id="SYNTHETIC-CARD",
        customer_id="SYNTHETIC-CUSTOMER",
        transaction_type="Purchase",
        transaction_category="Synthetic purchase",
        amount=42.0,
        currency="USD",
        amount_usd=42.0,
        channel=channel,
        merchant_name="Synthetic Merchant",
        merchant_category="Demo",
        transaction_country="Brazil",
        transaction_city="São Paulo",
        transaction_status="Approved",
        is_fraud=False,
    )


class DisputeClassificationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = DisputeClassificationService()

    def test_card_absent_unauthorized_maps_to_visa_10_4(self):
        result = self.service.classify(
            transaction(channel="E-commerce"),
            DisputeAllegation.UNAUTHORIZED_CARD,
            DisputeEvidence(customer_denies_authorization=True),
        )

        self.assertEqual(result.status, ClassificationStatus.VISA_CODE_CANDIDATE)
        self.assertEqual(result.visa_condition_code, "10.4")
        self.assertEqual(result.workflow, VisaWorkflow.ALLOCATION)
        self.assertIn("transaction_channel_card_absent", result.supporting_evidence)

    def test_card_present_unauthorized_maps_to_visa_10_3(self):
        result = self.service.classify(
            transaction(channel="POS"),
            DisputeAllegation.UNAUTHORIZED_CARD,
            DisputeEvidence(customer_denies_authorization=True),
        )

        self.assertEqual(result.visa_condition_code, "10.3")
        self.assertIn("transaction_channel_card_present", result.supporting_evidence)

    def test_duplicate_maps_to_visa_12_6_1(self):
        result = self.service.classify(
            transaction(),
            DisputeAllegation.DUPLICATE_PROCESSING,
            DisputeEvidence(customer_reports_duplicate=True),
        )

        self.assertEqual(result.status, ClassificationStatus.VISA_CODE_CANDIDATE)
        self.assertEqual(result.visa_condition_code, "12.6.1")
        self.assertEqual(result.workflow, VisaWorkflow.COLLABORATION)

    def test_unknown_channel_requires_clarification_and_accepts_customer_environment(self):
        unclear = self.service.classify(
            transaction(channel="Unknown"),
            DisputeAllegation.UNAUTHORIZED_CARD,
            DisputeEvidence(customer_denies_authorization=True),
        )

        self.assertEqual(unclear.status, ClassificationStatus.NEEDS_CLARIFICATION)
        self.assertIsNone(unclear.visa_condition_code)
        self.assertEqual(unclear.next_question_key, "verify_card_environment")

        clarified = self.service.classify(
            transaction(channel="Unknown"),
            DisputeAllegation.UNAUTHORIZED_CARD,
            DisputeEvidence(
                customer_denies_authorization=True,
                customer_reported_card_environment=CardEnvironment.CARD_PRESENT,
            ),
        )
        self.assertEqual(clarified.visa_condition_code, "10.3")
        self.assertIn("customer_report_card_present", clarified.supporting_evidence)

    def test_missing_required_evidence_does_not_assign_a_code(self):
        result = self.service.classify(
            transaction(),
            DisputeAllegation.UNAUTHORIZED_CARD,
            DisputeEvidence(),
        )

        self.assertEqual(result.status, ClassificationStatus.NEEDS_CLARIFICATION)
        self.assertIsNone(result.visa_condition_code)
        self.assertEqual(result.next_question_key, "confirm_authorization_denial")

    def test_conflicting_evidence_does_not_assign_a_code(self):
        result = self.service.classify(
            transaction(),
            DisputeAllegation.DUPLICATE_PROCESSING,
            DisputeEvidence(
                customer_denies_authorization=True,
                customer_reports_duplicate=True,
            ),
        )

        self.assertEqual(result.allegation, DisputeAllegation.INSUFFICIENT_INFO)
        self.assertEqual(result.status, ClassificationStatus.NEEDS_CLARIFICATION)
        self.assertIsNone(result.visa_condition_code)
        self.assertEqual(result.next_question_key, "resolve_fraud_or_duplicate")

    def test_telemetry_contains_metrics_but_not_transaction_id(self):
        with self.assertLogs("dispute_agent.dispute_classification", level="INFO") as logs:
            self.service.classify(
                transaction(),
                DisputeAllegation.INSUFFICIENT_INFO,
                DisputeEvidence(),
            )

        payload = json.loads(logs.records[-1].getMessage())
        self.assertEqual(payload["event"], "dispute.classification.completed")
        self.assertTrue(payload["clarification_required"])
        self.assertIn("latency_ms", payload)
        self.assertNotIn("transaction_id", payload)


if __name__ == "__main__":
    unittest.main()
