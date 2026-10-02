"""Shared, server-owned classification rules for the dispute demo."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from enum import StrEnum

from webapp.backend.models.transaction import Transaction

LOGGER = logging.getLogger(__name__)


class DisputeAllegation(StrEnum):
    """Customer-level claim before issuer evidence establishes a Visa condition."""

    UNAUTHORIZED_CARD = "UNAUTHORIZED_CARD"
    DUPLICATE_PROCESSING = "DUPLICATE_PROCESSING"
    INSUFFICIENT_INFO = "INSUFFICIENT_INFO"


class ClassificationStatus(StrEnum):
    """Whether the available evidence supports a Visa condition candidate."""

    VISA_CODE_CANDIDATE = "VISA_CODE_CANDIDATE"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"


class VisaWorkflow(StrEnum):
    ALLOCATION = "ALLOCATION"
    COLLABORATION = "COLLABORATION"


class CardEnvironment(StrEnum):
    CARD_PRESENT = "CARD_PRESENT"
    CARD_ABSENT = "CARD_ABSENT"


@dataclass(frozen=True)
class DisputeEvidence:
    """Facts supplied by the customer and the selected transaction record."""

    customer_denies_authorization: bool = False
    customer_reports_duplicate: bool = False
    customer_reported_card_environment: CardEnvironment | None = None


@dataclass(frozen=True)
class DisputeClassification:
    """Auditable classification stored with the synthetic call interaction."""

    allegation: DisputeAllegation
    status: ClassificationStatus
    transaction_id: str
    transaction_channel: str
    visa_condition_code: str | None
    visa_condition_name: str | None
    workflow: VisaWorkflow | None
    supporting_evidence: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    next_question_key: str | None


class DisputeClassificationService:
    """Validate model output and map supported allegations to Visa candidates."""

    def classify(
        self,
        transaction: Transaction,
        allegation: DisputeAllegation | str,
        evidence: DisputeEvidence,
    ) -> DisputeClassification:
        started = time.monotonic()
        parsed_allegation = DisputeAllegation(allegation)

        if parsed_allegation is DisputeAllegation.UNAUTHORIZED_CARD:
            result = self._unauthorized(transaction, evidence)
        elif parsed_allegation is DisputeAllegation.DUPLICATE_PROCESSING:
            result = self._duplicate(transaction, evidence)
        else:
            result = self._clarification(
                transaction,
                allegation=DisputeAllegation.INSUFFICIENT_INFO,
                missing=("customer_problem_type",),
                question="choose_fraud_or_duplicate",
            )

        LOGGER.info(
            json.dumps(
                {
                    "event": "dispute.classification.completed",
                    "allegation": result.allegation.value,
                    "status": result.status.value,
                    "visa_condition_code": result.visa_condition_code,
                    "transaction_channel": result.transaction_channel,
                    "clarification_required": (
                        result.status is ClassificationStatus.NEEDS_CLARIFICATION
                    ),
                    "latency_ms": round((time.monotonic() - started) * 1000, 2),
                }
            )
        )
        return result

    def _unauthorized(
        self,
        transaction: Transaction,
        evidence: DisputeEvidence,
    ) -> DisputeClassification:
        if not evidence.customer_denies_authorization:
            return self._clarification(
                transaction,
                allegation=DisputeAllegation.UNAUTHORIZED_CARD,
                missing=("explicit_authorization_denial",),
                question="confirm_authorization_denial",
            )

        if evidence.customer_reports_duplicate:
            return self._clarification(
                transaction,
                allegation=DisputeAllegation.INSUFFICIENT_INFO,
                missing=("resolve_conflicting_allegations",),
                question="resolve_fraud_or_duplicate",
            )

        card_environment = _card_environment(transaction.channel)
        environment_source = "transaction_channel"
        if card_environment is None and evidence.customer_reported_card_environment is not None:
            card_environment = evidence.customer_reported_card_environment
            environment_source = "customer_report"
        if card_environment is None:
            return self._clarification(
                transaction,
                allegation=DisputeAllegation.UNAUTHORIZED_CARD,
                missing=("transaction_card_environment",),
                question="verify_card_environment",
            )
        card_present = card_environment is CardEnvironment.CARD_PRESENT
        return DisputeClassification(
            allegation=DisputeAllegation.UNAUTHORIZED_CARD,
            status=ClassificationStatus.VISA_CODE_CANDIDATE,
            transaction_id=transaction.transaction_id,
            transaction_channel=transaction.channel,
            visa_condition_code="10.3" if card_present else "10.4",
            visa_condition_name=(
                "Other Fraud — Card-Present Environment"
                if card_present
                else "Other Fraud — Card-Absent Environment"
            ),
            workflow=VisaWorkflow.ALLOCATION,
            supporting_evidence=(
                "customer_explicitly_denies_authorization",
                f"{environment_source}_card_present"
                if card_present
                else f"{environment_source}_card_absent",
            ),
            missing_evidence=("issuer_eligibility_and_network_evidence_review",),
            next_question_key=None,
        )

    def _duplicate(
        self,
        transaction: Transaction,
        evidence: DisputeEvidence,
    ) -> DisputeClassification:
        if not evidence.customer_reports_duplicate:
            return self._clarification(
                transaction,
                allegation=DisputeAllegation.DUPLICATE_PROCESSING,
                missing=("explicit_same_purchase_charged_more_than_once",),
                question="confirm_duplicate_purchase",
            )

        if evidence.customer_denies_authorization:
            return self._clarification(
                transaction,
                allegation=DisputeAllegation.INSUFFICIENT_INFO,
                missing=("resolve_conflicting_allegations",),
                question="resolve_fraud_or_duplicate",
            )

        return DisputeClassification(
            allegation=DisputeAllegation.DUPLICATE_PROCESSING,
            status=ClassificationStatus.VISA_CODE_CANDIDATE,
            transaction_id=transaction.transaction_id,
            transaction_channel=transaction.channel,
            visa_condition_code="12.6.1",
            visa_condition_name="Duplicate Processing",
            workflow=VisaWorkflow.COLLABORATION,
            supporting_evidence=("customer_reports_same_purchase_charged_more_than_once",),
            missing_evidence=("matching_transaction_and_processing_evidence_review",),
            next_question_key=None,
        )

    @staticmethod
    def _clarification(
        transaction: Transaction,
        *,
        allegation: DisputeAllegation,
        missing: tuple[str, ...],
        question: str,
    ) -> DisputeClassification:
        return DisputeClassification(
            allegation=allegation,
            status=ClassificationStatus.NEEDS_CLARIFICATION,
            transaction_id=transaction.transaction_id,
            transaction_channel=transaction.channel,
            visa_condition_code=None,
            visa_condition_name=None,
            workflow=None,
            supporting_evidence=(),
            missing_evidence=missing,
            next_question_key=question,
        )


def _card_environment(channel: str) -> CardEnvironment | None:
    """Use the authoritative transaction channel and abstain when it is unknown."""
    normalized = " ".join(channel.casefold().replace("_", "-").split())
    if normalized in {"pos", "point-of-sale", "card present", "card-present"}:
        return CardEnvironment.CARD_PRESENT
    if normalized in {
        "e-commerce",
        "ecommerce",
        "online",
        "web",
        "card absent",
        "card-absent",
        "mail order",
        "telephone order",
    }:
        return CardEnvironment.CARD_ABSENT
    return None
