"""Server-owned state for synthetic phone and document authentication."""

from __future__ import annotations

import json
import logging
import secrets
import time
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from webapp.backend.models.transaction import Transaction
from webapp.backend.repositories.interfaces import CustomerRepository

from .caller_identity import (
    CallerIdentity,
    CallerIdentityStatus,
    VoiceCallerIdentityService,
    calling_code_from_phone,
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
    TRANSACTION_SELECTED = "transaction_selected"
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
    transaction_guess_attempts: int = 0
    transaction_search_attempts: int = 0
    handoff_reason: str | None = None


@dataclass(frozen=True)
class TransactionSelectionResult:
    state: VoiceCallState
    outcome: TransactionSelectionOutcome
    result_count: int = 0


class VoiceCallService:
    """Keep locale, authentication choices, identity, and DTMF server-owned."""

    def __init__(
        self,
        customer_source: str | Path | CustomerRepository,
        *,
        max_document_attempts: int = 3,
        transaction_repository: TransactionSearchRepository | None = None,
        max_transaction_guesses: int = 3,
    ) -> None:
        started = time.monotonic()
        self.identity = VoiceCallerIdentityService(customer_source)
        self.max_document_attempts = max_document_attempts
        self.max_transaction_guesses = max_transaction_guesses
        self.transactions = transaction_repository or SQLiteTransactionSearchRepository()
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
        locale = ConversationLocaleContext.explicit_choice(language, accent)

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

    def _authenticate_phone(self, state: VoiceCallState) -> VoiceCallState:
        """Authenticate using the number presented by the SIP call."""
        started = time.monotonic()
        previous_stage = state.stage
        result = self.identity.identify_phone(state.caller_phone)

        if result.status is CallerIdentityStatus.AUTHENTICATED:
            assert result.identity is not None
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
    ) -> TransactionSelectionResult:
        """Search the authenticated caller's transactions and propose one candidate."""

        state = self.get(call_id)
        self._require_transaction_search_stage(state)
        assert state.identity is not None
        if state.stage is VoiceCallStage.NEEDS_TRANSACTION_DETAILS and not criteria.has_any_filter:
            return self._request_transaction_refinement(
                state,
                state.transaction_criteria,
                reason="no_new_detail",
            )
        merged = criteria if replace_existing else state.transaction_criteria.merged_with(criteria)

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
            updated = replace(
                state,
                stage=VoiceCallStage.NEEDS_TRANSACTION_DETAILS,
                transaction_criteria=merged,
                transaction_candidates=(),
                current_transaction=None,
                transaction_search_attempts=search_attempts,
            )
            self._calls[call_id] = updated
            _telemetry(
                "voice.transaction.search_no_match",
                call_id=call_id,
                search_count=search_attempts,
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
                stage=VoiceCallStage.TRANSACTION_SELECTED,
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
            handoff_available=False,
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
