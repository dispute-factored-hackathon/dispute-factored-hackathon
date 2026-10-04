"""Create trackable call-center complaints from validated Visa classifications."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from webapp.backend.models.complaint import Complaint
from webapp.backend.models.transaction import Transaction
from webapp.backend.repositories.interfaces import ComplaintRepository


class UnsupportedVisaConditionError(ValueError):
    """Raised when intake has not produced a supported Visa condition."""


@dataclass(frozen=True)
class VisaComplaintTemplate:
    category: str
    subcategory: str
    description_label: str
    priority: str


VISA_COMPLAINT_TEMPLATES = {
    "10.3": VisaComplaintTemplate(
        category="Card Purchase",
        subcategory="Visa 10.3 · Other Fraud — Card-Present Environment",
        description_label="an unauthorized card-present transaction",
        priority="High",
    ),
    "10.4": VisaComplaintTemplate(
        category="Card Purchase",
        subcategory="Visa 10.4 · Other Fraud — Card-Absent Environment",
        description_label="an unauthorized card-absent transaction",
        priority="High",
    ),
    "12.6.1": VisaComplaintTemplate(
        category="Card Purchase",
        subcategory="Visa 12.6.1 · Duplicate Processing",
        description_label="duplicate processing of a recognized purchase",
        priority="Medium",
    ),
}


class ComplaintFilingService:
    """Persist one complaint per call using the replaceable repository contract."""

    def __init__(
        self, complaints: ComplaintRepository, *, reception_channel: str = "Call Center"
    ) -> None:
        self.complaints = complaints
        # "Call Center" for phone calls, "Web Chat" for the Izzy chat in the web app.
        self.reception_channel = reception_channel

    def file_from_call(
        self,
        *,
        call_id: str,
        customer_id: str,
        transaction: Transaction,
        visa_condition_code: str,
        now: datetime | None = None,
    ) -> Complaint:
        template = VISA_COMPLAINT_TEMPLATES.get(visa_condition_code)
        if template is None:
            raise UnsupportedVisaConditionError(
                f"unsupported Visa condition: {visa_condition_code}"
            )

        existing = self.complaints.get_by_origin_interaction(
            customer_id,
            call_id,
        )
        if existing is not None:
            return existing

        existing_complaints = self.complaints.list_by_customer(customer_id)
        created_at = now or datetime.now(UTC)
        merchant = transaction.merchant_name or "an unknown merchant"
        complaint_id = f"CMP-IZZY-{hashlib.sha256(call_id.encode()).hexdigest()[:16].upper()}"
        complaint = Complaint(
            complaint_id=complaint_id,
            creation_date=created_at,
            process_date=created_at.date(),
            customer_id=customer_id,
            case_type="Claim",
            category=template.category,
            subcategory=template.subcategory,
            reception_channel=self.reception_channel,
            affected_product_id=transaction.product_id,
            related_branch_id=transaction.branch_id,
            origin_interaction_id=call_id,
            description=(
                f"Customer reported {template.description_label} at {merchant} on "
                f"{transaction.transaction_date.date().isoformat()}. "
                f"Candidate Visa condition: {visa_condition_code}."
            ),
            claimed_amount=transaction.amount,
            currency=transaction.currency,
            priority=template.priority,
            status="In Review",
            assigned_agent_id="IZZY",
            assignment_date=created_at,
            first_response_date=created_at,
            sla_breached=False,
            is_repeat_complainer=bool(existing_complaints),
        )
        try:
            return self.complaints.create(complaint)
        except ValueError:
            repeated = self.complaints.get_by_id(complaint_id)
            if (
                repeated is not None
                and repeated.customer_id == customer_id
                and repeated.origin_interaction_id == call_id
            ):
                return repeated
            raise
