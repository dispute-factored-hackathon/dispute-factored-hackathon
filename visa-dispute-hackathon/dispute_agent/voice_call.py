"""Server-owned state for synthetic phone and document authentication."""

from __future__ import annotations

import json
import logging
import secrets
import time
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from webapp.backend.demo_card import seed_demo_card
from webapp.backend.models.transaction import Transaction
from webapp.backend.repositories.interfaces import (
    CallCenterInteractionRepository,
    CallTranscriptRepository,
    ComplaintRepository,
    CustomerRepository,
    ProductRepository,
    SatisfactionSurveyRepository,
    ServiceAgentRepository,
)
from webapp.backend.repositories.mock import (
    MockCallCenterInteractionRepository,
    MockCallTranscriptRepository,
    MockComplaintRepository,
    MockProductRepository,
    MockSatisfactionSurveyRepository,
    MockServiceAgentRepository,
)
from webapp.backend.services.call_interactions import CallInteractionService
from webapp.backend.services.complaint_filing import ComplaintFilingService
from webapp.backend.services.products import (
    ProductAccessDeniedError,
    ProductNotFoundError,
    ProductService,
)

from .caller_identity import (
    CallerIdentity,
    CallerIdentityStatus,
    VoiceCallerIdentityService,
    calling_code_from_phone,
)
from .dispute_classification import (
    CardEnvironment,
    ClassificationStatus,
    DisputeAllegation,
    DisputeClassification,
    DisputeClassificationService,
    DisputeEvidence,
)
from .language_context import ConversationLocaleContext
from .transaction_search import (
    InsufficientTransactionCriteriaError,
    SQLiteTransactionSearchRepository,
    TransactionSearchCriteria,
    TransactionSearchRepository,
)

LOGGER = logging.getLogger(__name__)


def _next_transaction_detail(
    criteria: TransactionSearchCriteria,
    requested_fields: tuple[str, ...],
) -> str:
    """Choose one useful missing detail without repeating an earlier question."""

    missing = (
        ("merchant", criteria.merchant_query is None),
        ("amount", criteria.approximate_amount is None),
        ("date", criteria.date_from is None and criteria.date_to is None),
        ("location", criteria.country is None and criteria.city is None),
        ("channel", criteria.channel is None),
    )
    for field_name, is_missing in missing:
        if is_missing and field_name not in requested_fields:
            return field_name
    for field_name, is_missing in missing:
        if is_missing:
            return field_name
    return "channel"


def _telemetry(event: str, *, call_id: str | None = None, **fields: Any) -> None:
    """Emit structured state-machine telemetry without sensitive identity values."""
    payload: dict[str, Any] = {"event": event}
    if call_id is not None:
        payload["call_id"] = call_id
    payload.update(fields)
    LOGGER.info(json.dumps(payload, ensure_ascii=False, default=str))


class VoiceCallStage(StrEnum):
    NEEDS_LANGUAGE_CONFIRMATION = "needs_language_confirmation"
    NEEDS_AUTH_METHOD = "needs_auth_method"
    NEEDS_DOCUMENT = "needs_document"
    AUTHENTICATED = "authenticated"
    NEEDS_TRANSACTION_DETAILS = "needs_transaction_details"
    CONFIRM_TRANSACTION = "confirm_transaction"
    NEEDS_DISPUTE_CLASSIFICATION = "needs_dispute_classification"
    DISPUTE_CLASSIFIED = "dispute_classified"
    COMPLETED = "completed"
    HANDOFF = "handoff"


class VoiceAuthenticationMethod(StrEnum):
    PHONE = "phone"
    DOCUMENT = "document"


class TransactionSelectionOutcome(StrEnum):
    NEEDS_CLARIFICATION = "needs_clarification"
    NO_MATCH = "no_match"
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    EXHAUSTED = "exhausted"


class DisputeClassificationOutcome(StrEnum):
    NEEDS_CLARIFICATION = "needs_clarification"
    CLASSIFIED = "classified"


class CardSecurityActionStatus(StrEnum):
    BLOCKED = "blocked"
    ALREADY_BLOCKED = "already_blocked"
    FAILED = "failed"


class ComplaintFilingStatus(StrEnum):
    FILED = "filed"
    FAILED = "failed"


@dataclass(frozen=True)
class VoiceCallState:
    call_id: str
    caller_phone: str
    stage: VoiceCallStage
    locale: ConversationLocaleContext
    identity: CallerIdentity | None = None
    authentication_method: VoiceAuthenticationMethod | None = None
    failed_document_attempts: int = 0
    document_digits: str = ""
    transaction_criteria: TransactionSearchCriteria = field(
        default_factory=TransactionSearchCriteria
    )
    transaction_candidates: tuple[Transaction, ...] = ()
    rejected_transaction_ids: tuple[str, ...] = ()
    requested_transaction_fields: tuple[str, ...] = ()
    pending_transaction_detail: str | None = None
    current_transaction: Transaction | None = None
    confirmed_transaction: Transaction | None = None
    dispute_classification: DisputeClassification | None = None
    card_security_action: CardSecurityActionStatus | None = None
    secured_card_last_four: str | None = None
    complaint_id: str | None = None
    complaint_status: str | None = None
    complaint_filing_status: ComplaintFilingStatus | None = None
    transaction_guess_attempts: int = 0
    transaction_search_attempts: int = 0
    transaction_no_match_attempts: int = 0
    handoff_reason: str | None = None


@dataclass(frozen=True)
class TransactionSelectionResult:
    state: VoiceCallState
    outcome: TransactionSelectionOutcome
    result_count: int = 0


@dataclass(frozen=True)
class DisputeClassificationResult:
    state: VoiceCallState
    outcome: DisputeClassificationOutcome


class VoiceCallService:
    """Keep locale, authentication choices, identity, and DTMF server-owned."""

    def __init__(
        self,
        customer_source: str | Path | CustomerRepository,
        *,
        max_document_attempts: int = 3,
        transaction_repository: TransactionSearchRepository | None = None,
        product_repository: ProductRepository | None = None,
        complaint_repository: ComplaintRepository | None = None,
        service_agent_repository: ServiceAgentRepository | None = None,
        interaction_repository: CallCenterInteractionRepository | None = None,
        transcript_repository: CallTranscriptRepository | None = None,
        satisfaction_survey_repository: SatisfactionSurveyRepository | None = None,
        transcription_model: str = "gpt-4o-mini-transcribe",
        max_transaction_guesses: int = 3,
    ) -> None:
        started = time.monotonic()
        self.identity = VoiceCallerIdentityService(customer_source)
        self.max_document_attempts = max_document_attempts
        self.max_transaction_guesses = max_transaction_guesses
        self.transactions = transaction_repository or SQLiteTransactionSearchRepository()
        self.products = product_repository or MockProductRepository()
        self.product_service = ProductService(self.products)
        self.complaints = complaint_repository or MockComplaintRepository()
        self.complaint_filing = ComplaintFilingService(self.complaints)
        self.call_interactions = CallInteractionService(
            service_agent_repository or MockServiceAgentRepository(),
            interaction_repository or MockCallCenterInteractionRepository(),
            transcript_repository or MockCallTranscriptRepository(),
            satisfaction_survey_repository or MockSatisfactionSurveyRepository(),
            transcription_model=transcription_model,
        )
        self.classifier = DisputeClassificationService()
        self._calls: dict[str, VoiceCallState] = {}
        _telemetry(
            "voice.service.initialized",
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            max_document_attempts=max_document_attempts,
            max_transaction_guesses=max_transaction_guesses,
        )

    def start(
        self,
        mobile_phone: str,
        *,
        call_id: str | None = None,
    ) -> VoiceCallState:
        """Initialize a call without authenticating the caller.

        The calling code is used only as a locale hint. Phone authentication is
        attempted later and only if the caller explicitly chooses that method.
        """
        started = time.monotonic()
        resolved_call_id = call_id or secrets.token_urlsafe(24)
        calling_code = calling_code_from_phone(mobile_phone)
        locale = ConversationLocaleContext.from_calling_code(calling_code)

        state = VoiceCallState(
            call_id=resolved_call_id,
            caller_phone=mobile_phone,
            stage=VoiceCallStage.NEEDS_LANGUAGE_CONFIRMATION,
            locale=locale,
        )
        self._calls[resolved_call_id] = state
        self.call_interactions.start(resolved_call_id)

        _telemetry(
            "voice.call.started",
            call_id=resolved_call_id,
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            stage=state.stage.value,
            language=state.locale.language,
            locale=state.locale.locale,
            accent=state.locale.accent,
            locale_source=state.locale.source,
            has_calling_code=calling_code is not None,
        )
        return state

    def confirm_language(self, call_id: str) -> VoiceCallState:
        """Keep the inferred language and proceed to authentication choice."""
        state = self.get(call_id)
        previous_stage = state.stage

        if state.stage is not VoiceCallStage.NEEDS_LANGUAGE_CONFIRMATION:
            return state

        updated = replace(state, stage=VoiceCallStage.NEEDS_AUTH_METHOD)
        self._calls[call_id] = updated

        _telemetry(
            "voice.language.confirmed",
            call_id=call_id,
            language=updated.locale.language,
            locale=updated.locale.locale,
            accent=updated.locale.accent,
        )
        self._log_stage_transition(
            call_id,
            previous_stage,
            updated.stage,
            reason="language_confirmed",
        )
        return updated

    def choose_language(
        self,
        call_id: str,
        *,
        language: str,
        accent: str | None = None,
    ) -> VoiceCallState:
        """Record an explicit supported-language choice."""
        started = time.monotonic()
        state = self.get(call_id)
        previous_stage = state.stage
        resolved_accent = accent
        if resolved_accent is None:
            if state.identity is not None:
                profile_locale = ConversationLocaleContext.from_customer_record(
                    country=state.identity.country,
                    detected_accent=state.identity.detected_accent,
                )
                if profile_locale.language == language:
                    resolved_accent = profile_locale.accent
            if resolved_accent is None:
                calling_code_locale = ConversationLocaleContext.from_calling_code(
                    calling_code_from_phone(state.caller_phone)
                )
                if calling_code_locale.language == language:
                    resolved_accent = calling_code_locale.accent
            if resolved_accent is None and state.locale.language == language:
                resolved_accent = state.locale.accent
        locale = ConversationLocaleContext.explicit_choice(language, resolved_accent)

        next_stage = (
            VoiceCallStage.NEEDS_AUTH_METHOD
            if state.stage is VoiceCallStage.NEEDS_LANGUAGE_CONFIRMATION
            else state.stage
        )

        updated = replace(
            state,
            stage=next_stage,
            locale=locale,
        )
        self._calls[call_id] = updated

        _telemetry(
            "voice.language.selected",
            call_id=call_id,
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            language=updated.locale.language,
            locale=updated.locale.locale,
            accent=updated.locale.accent,
        )
        self._log_stage_transition(
            call_id,
            previous_stage,
            updated.stage,
            reason="language_selected",
        )
        return updated

    def choose_authentication_method(
        self,
        call_id: str,
        *,
        method: str,
    ) -> VoiceCallState:
        """Apply the caller's authentication-method choice."""
        state = self.get(call_id)

        if state.stage is not VoiceCallStage.NEEDS_AUTH_METHOD:
            raise ValueError(
                "authentication method can only be selected after language confirmation"
            )

        try:
            authentication_method = VoiceAuthenticationMethod(method.strip().casefold())
        except ValueError as error:
            raise ValueError("authentication method must be phone or document") from error

        _telemetry(
            "voice.authentication.method_selected",
            call_id=call_id,
            method=authentication_method.value,
        )

        if authentication_method is VoiceAuthenticationMethod.PHONE:
            return self._authenticate_phone(state)

        previous_stage = state.stage
        updated = replace(
            state,
            stage=VoiceCallStage.NEEDS_DOCUMENT,
            authentication_method=VoiceAuthenticationMethod.DOCUMENT,
            document_digits="",
        )
        self._calls[call_id] = updated
        self._log_stage_transition(
            call_id,
            previous_stage,
            updated.stage,
            reason="document_authentication_selected",
        )
        return updated

    def request_human(
        self,
        call_id: str,
        *,
        reason: str = "customer_requested",
    ) -> VoiceCallState:
        """Preserve the current context and move an active call to human handoff."""

        state = self.get(call_id)
        if state.stage is VoiceCallStage.COMPLETED:
            raise ValueError("a completed call cannot be transferred")
        if state.stage is VoiceCallStage.HANDOFF:
            return state

        updated = replace(
            state,
            stage=VoiceCallStage.HANDOFF,
            handoff_reason=reason,
        )
        self._calls[call_id] = updated
        self.call_interactions.sync(updated)
        self._log_stage_transition(
            call_id,
            state.stage,
            updated.stage,
            reason=reason,
        )
        _telemetry(
            "voice.handoff.requested",
            call_id=call_id,
            reason=reason,
            authenticated=state.identity is not None,
            from_stage=state.stage.value,
        )
        return updated

    def _authenticate_phone(self, state: VoiceCallState) -> VoiceCallState:
        """Authenticate using the number presented by the SIP call."""
        started = time.monotonic()
        previous_stage = state.stage
        result = self.identity.identify_phone(state.caller_phone)

        if result.status is CallerIdentityStatus.AUTHENTICATED:
            assert result.identity is not None
            seed_demo_card(self.products, result.identity.customer_id)
            updated = replace(
                state,
                stage=VoiceCallStage.AUTHENTICATED,
                identity=result.identity,
                authentication_method=VoiceAuthenticationMethod.PHONE,
                document_digits="",
            )
            _telemetry(
                "voice.authentication.succeeded",
                call_id=state.call_id,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                method="phone",
            )
            reason = "phone_authenticated"
        else:
            updated = replace(
                state,
                stage=VoiceCallStage.NEEDS_DOCUMENT,
                identity=None,
                authentication_method=VoiceAuthenticationMethod.DOCUMENT,
                document_digits="",
            )
            _telemetry(
                "voice.authentication.failed",
                call_id=state.call_id,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                method="phone",
                outcome="document_fallback",
                identity_status=result.status.value,
            )
            reason = "phone_authentication_failed"

        self._calls[state.call_id] = updated
        self.call_interactions.sync(updated)
        self._log_stage_transition(
            state.call_id,
            previous_stage,
            updated.stage,
            reason=reason,
        )
        return updated

    def receive_dtmf(
        self,
        call_id: str,
        key: str,
    ) -> tuple[VoiceCallState, bool]:
        """Consume DTMF without logging the actual keypad digit."""
        state = self.get(call_id)

        _telemetry(
            "voice.dtmf.received",
            call_id=call_id,
            stage=state.stage.value,
            digit_count_before=len(state.document_digits),
        )

        if state.stage is not VoiceCallStage.NEEDS_DOCUMENT:
            _telemetry(
                "voice.dtmf.ignored",
                call_id=call_id,
                stage=state.stage.value,
                reason="stage_not_needs_document",
            )
            return state, False

        if len(key) != 1 or key not in "0123456789*#":
            _telemetry(
                "voice.dtmf.invalid",
                call_id=call_id,
                reason="unsupported_key",
            )
            raise ValueError("DTMF key must be one of 0-9, *, or #")

        if key == "*":
            updated = replace(state, document_digits="")
            should_respond = True
            _telemetry("voice.document_entry.cleared", call_id=call_id)

        elif key == "#":
            if not state.document_digits:
                _telemetry("voice.document_entry.submitted_empty", call_id=call_id)
                return state, True

            _telemetry(
                "voice.document_entry.submitted",
                call_id=call_id,
                digit_count=len(state.document_digits),
                failed_attempts_before=state.failed_document_attempts,
            )
            return self._authenticate_document(state), True

        else:
            if len(state.document_digits) >= 24:
                _telemetry(
                    "voice.document_entry.too_long",
                    call_id=call_id,
                    digit_count=len(state.document_digits),
                )
                raise ValueError("document entry is too long")

            updated = replace(
                state,
                document_digits=f"{state.document_digits}{key}",
            )
            should_respond = False
            _telemetry(
                "voice.document_entry.progress",
                call_id=call_id,
                digit_count=len(updated.document_digits),
            )

        self._calls[call_id] = updated
        return updated, should_respond

    def _authenticate_document(self, state: VoiceCallState) -> VoiceCallState:
        started = time.monotonic()
        previous_stage = state.stage
        digit_count = len(state.document_digits)
        result = self.identity.identify_document(state.document_digits)

        if result.status is CallerIdentityStatus.AUTHENTICATED:
            assert result.identity is not None
            seed_demo_card(self.products, result.identity.customer_id)
            updated = replace(
                state,
                stage=VoiceCallStage.AUTHENTICATED,
                identity=result.identity,
                authentication_method=VoiceAuthenticationMethod.DOCUMENT,
                document_digits="",
            )
            _telemetry(
                "voice.authentication.succeeded",
                call_id=state.call_id,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                method="document",
                digit_count=digit_count,
                failed_attempts=state.failed_document_attempts,
            )
        else:
            attempts = state.failed_document_attempts + 1
            updated = replace(
                state,
                stage=(
                    VoiceCallStage.HANDOFF
                    if attempts >= self.max_document_attempts
                    else VoiceCallStage.NEEDS_DOCUMENT
                ),
                identity=None,
                authentication_method=VoiceAuthenticationMethod.DOCUMENT,
                failed_document_attempts=attempts,
                document_digits="",
                handoff_reason=(
                    "authentication_attempts_exhausted"
                    if attempts >= self.max_document_attempts
                    else state.handoff_reason
                ),
            )
            _telemetry(
                "voice.authentication.failed",
                call_id=state.call_id,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                method="document",
                digit_count=digit_count,
                failed_attempts=attempts,
                max_attempts=self.max_document_attempts,
                outcome=("handoff" if updated.stage is VoiceCallStage.HANDOFF else "retry"),
                identity_status=result.status.value,
            )

        self._calls[state.call_id] = updated
        self.call_interactions.sync(updated)

        if previous_stage is not updated.stage:
            self._log_stage_transition(
                state.call_id,
                previous_stage,
                updated.stage,
                reason=(
                    "document_authenticated"
                    if updated.stage is VoiceCallStage.AUTHENTICATED
                    else "max_document_attempts"
                    if updated.stage is VoiceCallStage.HANDOFF
                    else "document_authentication_failed"
                ),
            )

        return updated

    def search_transactions(
        self,
        call_id: str,
        criteria: TransactionSearchCriteria,
        *,
        replace_existing: bool = False,
        clear_filters: bool = False,
        remove_filters: tuple[str, ...] = (),
    ) -> TransactionSelectionResult:
        """Search the authenticated caller's transactions and propose one candidate."""

        state = self.get(call_id)
        self._require_transaction_search_stage(state)
        assert state.identity is not None
        filters_changed = replace_existing or clear_filters or bool(remove_filters)
        if (
            state.stage is VoiceCallStage.NEEDS_TRANSACTION_DETAILS
            and not criteria.has_any_filter
            and not filters_changed
        ):
            return self._request_transaction_refinement(
                state,
                state.transaction_criteria,
                reason="no_new_detail",
            )
        base = TransactionSearchCriteria() if clear_filters else state.transaction_criteria
        base = base.without(remove_filters)
        merged = criteria if replace_existing else base.merged_with(criteria)

        if not merged.is_discriminative:
            return self._request_transaction_refinement(
                state,
                merged,
                reason="insufficient_criteria",
            )

        search_attempts = state.transaction_search_attempts + 1
        try:
            search = self.transactions.search(
                state.identity.customer_id,
                merged,
                excluded_transaction_ids=state.rejected_transaction_ids,
            )
        except InsufficientTransactionCriteriaError:
            return self._request_transaction_refinement(
                replace(state, transaction_search_attempts=search_attempts),
                merged,
                reason="repository_requires_more_detail",
            )

        if not search.transactions:
            no_match_attempts = state.transaction_no_match_attempts + 1
            if no_match_attempts >= self.max_transaction_guesses:
                return self._transaction_handoff(
                    replace(
                        state,
                        transaction_criteria=merged,
                        transaction_search_attempts=search_attempts,
                        transaction_no_match_attempts=no_match_attempts,
                    )
                )
            updated = replace(
                state,
                stage=VoiceCallStage.NEEDS_TRANSACTION_DETAILS,
                transaction_criteria=merged,
                transaction_candidates=(),
                current_transaction=None,
                transaction_search_attempts=search_attempts,
                transaction_no_match_attempts=no_match_attempts,
            )
            self._calls[call_id] = updated
            _telemetry(
                "voice.transaction.search_no_match",
                call_id=call_id,
                search_count=search_attempts,
                no_match_count=no_match_attempts,
                active_filters=dict(merged.active_filters()),
            )
            return TransactionSelectionResult(
                updated,
                TransactionSelectionOutcome.NO_MATCH,
            )

        return self._propose_transaction(
            replace(
                state,
                transaction_criteria=merged,
                transaction_candidates=search.transactions,
                transaction_search_attempts=search_attempts,
            ),
            search.transactions[0],
            result_count=len(search.transactions),
        )

    def resolve_transaction_candidate(
        self,
        call_id: str,
        *,
        confirmed: bool,
    ) -> TransactionSelectionResult:
        """Apply an explicit yes/no answer to the currently spoken transaction."""

        state = self.get(call_id)
        if state.stage is not VoiceCallStage.CONFIRM_TRANSACTION:
            raise ValueError("there is no transaction awaiting confirmation")
        if state.current_transaction is None:
            raise ValueError("the current transaction candidate is missing")

        if confirmed:
            updated = replace(
                state,
                stage=VoiceCallStage.NEEDS_DISPUTE_CLASSIFICATION,
                confirmed_transaction=state.current_transaction,
            )
            self._calls[call_id] = updated
            _telemetry(
                "voice.transaction.confirmed",
                call_id=call_id,
                guess_number=state.transaction_guess_attempts,
            )
            return TransactionSelectionResult(
                updated,
                TransactionSelectionOutcome.CONFIRMED,
                result_count=len(state.transaction_candidates),
            )

        _telemetry(
            "voice.transaction.denied",
            call_id=call_id,
            guess_number=state.transaction_guess_attempts,
        )
        if state.transaction_guess_attempts >= self.max_transaction_guesses:
            return self._transaction_handoff(state)

        rejected_ids = (
            *state.rejected_transaction_ids,
            state.current_transaction.transaction_id,
        )
        return self._request_transaction_refinement(
            state,
            state.transaction_criteria,
            reason="candidate_denied",
            rejected_transaction_ids=rejected_ids,
        )

    def classify_dispute(
        self,
        call_id: str,
        *,
        allegation: DisputeAllegation | str,
        customer_denies_authorization: bool = False,
        customer_reports_duplicate: bool = False,
        customer_reported_card_environment: CardEnvironment | str | None = None,
    ) -> DisputeClassificationResult:
        """Validate the allegation and store an auditable Visa condition candidate."""
        state = self.get(call_id)
        if state.stage is not VoiceCallStage.NEEDS_DISPUTE_CLASSIFICATION:
            raise ValueError("dispute classification requires a confirmed transaction")
        if state.confirmed_transaction is None:
            raise ValueError("the confirmed transaction is missing")

        classification = self.classifier.classify(
            state.confirmed_transaction,
            allegation,
            DisputeEvidence(
                customer_denies_authorization=customer_denies_authorization,
                customer_reports_duplicate=customer_reports_duplicate,
                customer_reported_card_environment=(
                    CardEnvironment(customer_reported_card_environment)
                    if customer_reported_card_environment is not None
                    else None
                ),
            ),
        )
        outcome = (
            DisputeClassificationOutcome.CLASSIFIED
            if classification.status is ClassificationStatus.VISA_CODE_CANDIDATE
            else DisputeClassificationOutcome.NEEDS_CLARIFICATION
        )
        updated = replace(
            state,
            stage=(
                VoiceCallStage.DISPUTE_CLASSIFIED
                if outcome is DisputeClassificationOutcome.CLASSIFIED
                else VoiceCallStage.NEEDS_DISPUTE_CLASSIFICATION
            ),
            dispute_classification=classification,
        )
        if (
            outcome is DisputeClassificationOutcome.CLASSIFIED
            and classification.allegation is DisputeAllegation.UNAUTHORIZED_CARD
        ):
            updated = self._block_confirmed_transaction_card(updated)
        if outcome is DisputeClassificationOutcome.CLASSIFIED:
            updated = self._file_classified_complaint(updated)
        self._calls[call_id] = updated
        self.call_interactions.sync(updated)
        _telemetry(
            "voice.dispute.classification_stored",
            call_id=call_id,
            allegation=classification.allegation.value,
            status=classification.status.value,
            visa_condition_code=classification.visa_condition_code,
            outcome=outcome.value,
        )
        return DisputeClassificationResult(updated, outcome)

    def _file_classified_complaint(self, state: VoiceCallState) -> VoiceCallState:
        """Persist the validated intake result without letting the model own the write."""
        assert state.identity is not None
        assert state.confirmed_transaction is not None
        assert state.dispute_classification is not None
        assert state.dispute_classification.visa_condition_code is not None
        self.call_interactions.sync(state)
        try:
            complaint = self.complaint_filing.file_from_call(
                call_id=self.call_interactions.interaction_id(state.call_id),
                customer_id=state.identity.customer_id,
                transaction=state.confirmed_transaction,
                visa_condition_code=state.dispute_classification.visa_condition_code,
            )
        except Exception as error:
            LOGGER.exception("Failed to file complaint for call %s", state.call_id)
            _telemetry(
                "voice.complaint.filing_failed",
                call_id=state.call_id,
                error_type=type(error).__name__,
            )
            return replace(
                state,
                complaint_filing_status=ComplaintFilingStatus.FAILED,
            )

        _telemetry(
            "voice.complaint.filed",
            call_id=state.call_id,
            complaint_id=complaint.complaint_id,
            status=complaint.status,
            visa_condition_code=state.dispute_classification.visa_condition_code,
        )
        return replace(
            state,
            complaint_id=complaint.complaint_id,
            complaint_status=complaint.status,
            complaint_filing_status=ComplaintFilingStatus.FILED,
        )

    def record_transcript_turn(
        self, call_id: str, *, speaker: Literal["customer", "agent"], text: str
    ) -> None:
        if speaker not in {"customer", "agent"}:
            raise ValueError("speaker must be customer or agent")
        self.call_interactions.record_turn(self.get(call_id), speaker, text)

    def sync_interaction(self, call_id: str) -> None:
        self.call_interactions.sync(self.get(call_id))

    def record_csat(self, call_id: str, *, rating: int) -> VoiceCallState:
        state = self.get(call_id)
        if state.stage is not VoiceCallStage.DISPUTE_CLASSIFIED:
            raise ValueError("CSAT can only be recorded after dispute classification")
        self.call_interactions.record_csat(state, rating)
        updated = replace(state, stage=VoiceCallStage.COMPLETED)
        self._calls[call_id] = updated
        self.call_interactions.sync(updated)
        return updated

    def decline_csat(self, call_id: str) -> VoiceCallState:
        state = self.get(call_id)
        if state.stage is not VoiceCallStage.DISPUTE_CLASSIFIED:
            raise ValueError("CSAT can only be declined after dispute classification")
        updated = replace(state, stage=VoiceCallStage.COMPLETED)
        self._calls[call_id] = updated
        self.call_interactions.sync(updated)
        return updated

    def finalize(self, call_id: str) -> None:
        self.call_interactions.finalize(self.get(call_id))

    def _block_confirmed_transaction_card(self, state: VoiceCallState) -> VoiceCallState:
        """Apply the deterministic safety action after validated fraud classification."""
        assert state.identity is not None
        assert state.confirmed_transaction is not None
        product_id = state.confirmed_transaction.product_id
        try:
            product = self.products.get_by_id(product_id)
            if product is None:
                raise ProductNotFoundError
            was_blocked = product.product_status == "Blocked"
            blocked = self.product_service.block(product_id, state.identity.customer_id)
        except (ProductNotFoundError, ProductAccessDeniedError, ValueError):
            _telemetry(
                "voice.card.block_failed",
                call_id=state.call_id,
                product_id=product_id,
                reason="product_unavailable_or_not_owned",
            )
            return replace(
                state,
                card_security_action=CardSecurityActionStatus.FAILED,
                secured_card_last_four=None,
            )

        status = (
            CardSecurityActionStatus.ALREADY_BLOCKED
            if was_blocked
            else CardSecurityActionStatus.BLOCKED
        )
        last_four = blocked.product_number[-4:]
        _telemetry(
            "voice.card.blocked",
            call_id=state.call_id,
            product_id=product_id,
            status=status.value,
            card_last_four=last_four,
        )
        return replace(
            state,
            card_security_action=status,
            secured_card_last_four=last_four,
        )

    def _propose_transaction(
        self,
        state: VoiceCallState,
        transaction: Transaction,
        *,
        result_count: int,
    ) -> TransactionSelectionResult:
        replacing_current_candidate = state.stage is VoiceCallStage.CONFIRM_TRANSACTION
        attempts = (
            state.transaction_guess_attempts
            if replacing_current_candidate
            else state.transaction_guess_attempts + 1
        )
        updated = replace(
            state,
            stage=VoiceCallStage.CONFIRM_TRANSACTION,
            current_transaction=transaction,
            transaction_guess_attempts=attempts,
            pending_transaction_detail=None,
        )
        self._calls[state.call_id] = updated
        _telemetry(
            "voice.transaction.candidate_proposed",
            call_id=state.call_id,
            guess_number=attempts,
            result_count=result_count,
            active_filters=dict(updated.transaction_criteria.active_filters()),
        )
        return TransactionSelectionResult(
            updated,
            TransactionSelectionOutcome.CANDIDATE,
            result_count=result_count,
        )

    def _request_transaction_refinement(
        self,
        state: VoiceCallState,
        criteria: TransactionSearchCriteria,
        *,
        reason: str,
        rejected_transaction_ids: tuple[str, ...] | None = None,
    ) -> TransactionSelectionResult:
        requested_field = _next_transaction_detail(
            criteria,
            state.requested_transaction_fields,
        )
        requested_fields = state.requested_transaction_fields
        if requested_field not in requested_fields:
            requested_fields = (*requested_fields, requested_field)
        updated = replace(
            state,
            stage=VoiceCallStage.NEEDS_TRANSACTION_DETAILS,
            transaction_criteria=criteria,
            transaction_candidates=(),
            current_transaction=None,
            rejected_transaction_ids=(
                rejected_transaction_ids
                if rejected_transaction_ids is not None
                else state.rejected_transaction_ids
            ),
            requested_transaction_fields=requested_fields,
            pending_transaction_detail=requested_field,
        )
        self._calls[state.call_id] = updated
        _telemetry(
            "voice.transaction.refinement_requested",
            call_id=state.call_id,
            reason=reason,
            requested_field=requested_field,
            guess_number=state.transaction_guess_attempts,
        )
        return TransactionSelectionResult(
            updated,
            TransactionSelectionOutcome.NEEDS_CLARIFICATION,
        )

    def _transaction_handoff(self, state: VoiceCallState) -> TransactionSelectionResult:
        updated = replace(
            state,
            stage=VoiceCallStage.HANDOFF,
            current_transaction=None,
            handoff_reason="transaction_search_exhausted",
        )
        self._calls[state.call_id] = updated
        _telemetry(
            "voice.transaction.search_exhausted",
            call_id=state.call_id,
            guess_count=state.transaction_guess_attempts,
            no_match_count=state.transaction_no_match_attempts,
            active_filters=dict(state.transaction_criteria.active_filters()),
            handoff_requested=True,
        )
        return TransactionSelectionResult(
            updated,
            TransactionSelectionOutcome.EXHAUSTED,
        )

    @staticmethod
    def _require_transaction_search_stage(state: VoiceCallState) -> None:
        if state.identity is None or state.stage not in {
            VoiceCallStage.AUTHENTICATED,
            VoiceCallStage.NEEDS_TRANSACTION_DETAILS,
            VoiceCallStage.CONFIRM_TRANSACTION,
        }:
            raise ValueError("transaction search requires an authenticated caller")

    def get(self, call_id: str) -> VoiceCallState:
        try:
            return self._calls[call_id]
        except KeyError as error:
            _telemetry("voice.call.not_found", call_id=call_id)
            raise ValueError("voice call does not exist") from error

    @staticmethod
    def _log_stage_transition(
        call_id: str,
        previous_stage: VoiceCallStage,
        next_stage: VoiceCallStage,
        *,
        reason: str,
    ) -> None:
        if previous_stage is next_stage:
            return

        _telemetry(
            "voice.stage.transition",
            call_id=call_id,
            from_stage=previous_stage.value,
            to_stage=next_stage.value,
            reason=reason,
        )
