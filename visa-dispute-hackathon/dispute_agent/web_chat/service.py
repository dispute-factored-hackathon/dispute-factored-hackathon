"""Web chat entry points on top of the voice dispute workflow.

`WebChatDisputeService` reuses every `VoiceCallService` stage after transaction selection (Visa
classification, card blocking, complaint filing, CSAT, handoff) and writes to the same PostgreSQL
as the app and the voice agent. It only adds what the web needs and leaves calls untouched:

* the customer is already authenticated by the web session, so a chat starts at AUTHENTICATED;
* the customer's card purchases (lakehouse + PostgreSQL) are searched and offered as up to three
  options, and the customer picks one or rejects them all;
* a purchase opened in the web app can be offered directly;
* interactions and complaints are recorded with the Web Chat channel.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any

from webapp.backend.models.card_transaction import CardTransaction
from webapp.backend.models.customer import Customer
from webapp.backend.repositories.interfaces import (
    CardPurchaseRepository,
    CustomerRepository,
    Repositories,
    TransactionRepository,
)
from webapp.backend.services.call_interactions import WEB_CHAT_CHANNEL, CallInteractionService
from webapp.backend.services.complaint_filing import ComplaintFilingService

from ..caller_identity import VoiceCallerIdentityService
from ..language_context import ConversationLocaleContext
from ..transaction_search import InsufficientTransactionCriteriaError
from ..voice_call import (
    TransactionSelectionOutcome,
    TransactionSelectionResult,
    VoiceCallService,
    VoiceCallStage,
    VoiceCallState,
    _telemetry,
    voice_repository_arguments,
)
from .search import CardPurchaseCriteria, CardPurchaseSearch

WEB_SESSION_ASSURANCE = "DEMO_ONLY_WEB_SESSION"
SUPPORTED_LANGUAGES = {"en", "pt", "es"}
# A purchase at or above this fraud-model score is proposed as possibly unauthorized.
FRAUD_SCORE_SUGGESTION = 0.8
SEARCH_STAGES = {
    VoiceCallStage.AUTHENTICATED,
    VoiceCallStage.NEEDS_TRANSACTION_DETAILS,
    VoiceCallStage.CONFIRM_TRANSACTION,
}


def chat_locale(customer: Customer, requested_locale: str | None) -> ConversationLocaleContext:
    """Use the language the customer sees in the web app, falling back to their profile."""

    locale = (requested_locale or customer.interface_locale.value).strip()
    language = locale.split("-")[0].casefold()
    if language not in SUPPORTED_LANGUAGES:
        language = customer.interface_locale.value.split("-")[0]
    accent = locale.replace("-", "_") if "-" in locale else None
    for candidate in (accent, customer.detected_accent.value, None):
        try:
            return ConversationLocaleContext.explicit_choice(language, candidate)
        except ValueError:
            continue
    return ConversationLocaleContext.explicit_choice("en")


@dataclass(frozen=True)
class OptionsResult:
    """Outcome of a web search: options offered, or why none were."""

    state: VoiceCallState
    outcome: TransactionSelectionOutcome
    options: tuple[CardTransaction, ...] = ()


class WebChatDisputeService(VoiceCallService):
    """The voice dispute workflow, entered from an authenticated web session."""

    def __init__(
        self,
        customers: CustomerRepository,
        transactions: TransactionRepository,
        purchases: CardPurchaseRepository,
        **repository_arguments: Any,
    ) -> None:
        super().__init__(customers, **repository_arguments)
        self.transaction_records = transactions
        self.purchases = purchases
        self.purchase_search = CardPurchaseSearch(purchases)
        self._options: dict[str, tuple[CardTransaction, ...]] = {}
        self._suggestions: dict[str, str] = {}
        self.complaint_filing = ComplaintFilingService(
            self.complaints, reception_channel="Web Chat"
        )
        self.call_interactions = CallInteractionService(
            repository_arguments["service_agent_repository"],
            repository_arguments["interaction_repository"],
            repository_arguments["transcript_repository"],
            repository_arguments["satisfaction_survey_repository"],
            transcription_model="none (typed web chat)",
            channel=WEB_CHAT_CHANNEL,
        )

    @classmethod
    def from_repositories(
        cls,
        repositories: Repositories,
        *,
        purchases: CardPurchaseRepository | None = None,
    ) -> WebChatDisputeService:
        return cls(
            repositories.customers,
            repositories.transactions,
            purchases or repositories.card_purchases,
            **voice_repository_arguments(repositories),
        )

    # ------------------------------------------------------------------ session

    def start_session(
        self,
        session_id: str,
        customer: Customer,
        *,
        locale: str | None = None,
    ) -> VoiceCallState:
        """Open a chat for the customer resolved from the web session cookie."""

        state = VoiceCallState(
            call_id=session_id,
            caller_phone=customer.mobile_phone or "",
            stage=VoiceCallStage.AUTHENTICATED,
            locale=chat_locale(customer, locale),
            identity=VoiceCallerIdentityService._identity_from_customer(
                customer, WEB_SESSION_ASSURANCE
            ),
            transaction_criteria=CardPurchaseCriteria(),
        )
        self._calls[session_id] = state
        self.call_interactions.start(session_id)
        self.call_interactions.sync(state)
        _telemetry(
            "web_chat.session.started",
            call_id=session_id,
            language=state.locale.language,
            locale=state.locale.locale,
        )
        return state

    def options(self, session_id: str) -> tuple[CardTransaction, ...]:
        """The purchases currently offered to the customer (with card context)."""

        state = self.get(session_id)
        if state.stage is not VoiceCallStage.CONFIRM_TRANSACTION:
            return ()
        return self._options.get(session_id, ())

    def selected_purchase(self, session_id: str) -> CardTransaction | None:
        state = self.get(session_id)
        transaction = state.confirmed_transaction
        if transaction is None or state.identity is None:
            return None
        return self.purchases.get_for_customer(
            state.identity.customer_id, transaction.transaction_id
        )

    # ------------------------------------------------------------------ search and selection

    def propose_known_transaction(
        self, session_id: str, transaction_id: str
    ) -> OptionsResult | None:
        """Offer a purchase the customer opened in the web app as the only option.

        Returns None, without revealing whether the id exists, unless it is a card purchase of the
        authenticated customer.
        """

        state = self.get(session_id)
        assert state.identity is not None
        if state.stage is not VoiceCallStage.AUTHENTICATED:
            return None
        purchase = self.purchases.get_for_customer(state.identity.customer_id, transaction_id)
        if purchase is None:
            _telemetry("web_chat.transaction_context.ignored", call_id=session_id)
            return None
        _telemetry("web_chat.transaction_context.accepted", call_id=session_id)
        return self._offer(state, (purchase,))

    def select_known_transaction(
        self, session_id: str, transaction_id: str
    ) -> TransactionSelectionResult | None:
        """The customer chose this purchase in the web app: select it without asking again.

        Returns None (and leaves the chat at the start) unless it is a card purchase of the
        authenticated customer.
        """

        if self.propose_known_transaction(session_id, transaction_id) is None:
            return None
        return self.select_option(session_id, transaction_id)

    def search_options(
        self,
        session_id: str,
        criteria: CardPurchaseCriteria,
        *,
        clear_filters: bool = False,
        remove_filters: tuple[str, ...] = (),
    ) -> OptionsResult:
        """Search the customer's card purchases and offer up to three options."""

        state = self.get(session_id)
        if state.identity is None or state.stage not in SEARCH_STAGES:
            raise ValueError("transaction search requires an authenticated customer")
        filters_changed = clear_filters or bool(remove_filters)
        if (
            state.stage is VoiceCallStage.NEEDS_TRANSACTION_DETAILS
            and not criteria.has_any_filter
            and not filters_changed
        ):
            return self._refine(state, state.transaction_criteria, reason="no_new_detail")
        base = (
            CardPurchaseCriteria()
            if clear_filters
            else CardPurchaseCriteria.upgrade(state.transaction_criteria)
        )
        merged = base.without(remove_filters).merged_with(criteria)
        if not merged.is_discriminative:
            return self._refine(state, merged, reason="insufficient_criteria")

        searched = replace(
            state,
            transaction_criteria=merged,
            transaction_search_attempts=state.transaction_search_attempts + 1,
        )
        try:
            found = self.purchase_search.search(
                state.identity.customer_id,
                merged,
                excluded_transaction_ids=state.rejected_transaction_ids,
            )
        except InsufficientTransactionCriteriaError:
            return self._refine(searched, merged, reason="repository_requires_more_detail")

        if not found:
            no_match_attempts = state.transaction_no_match_attempts + 1
            searched = replace(searched, transaction_no_match_attempts=no_match_attempts)
            if no_match_attempts >= self.max_transaction_guesses:
                return self._as_options(self._transaction_handoff(searched))
            updated = replace(
                searched,
                stage=VoiceCallStage.NEEDS_TRANSACTION_DETAILS,
                transaction_candidates=(),
                current_transaction=None,
            )
            self._calls[session_id] = updated
            self._options.pop(session_id, None)
            _telemetry("web_chat.transaction.search_no_match", call_id=session_id)
            return OptionsResult(updated, TransactionSelectionOutcome.NO_MATCH)

        return self._offer(searched, tuple(option.purchase for option in found))

    def select_option(self, session_id: str, transaction_id: str) -> TransactionSelectionResult:
        """Accept the customer's choice; only an option that was offered can be selected."""

        state = self.get(session_id)
        offered = {item.transaction.transaction_id: item for item in self.options(session_id)}
        chosen = offered.get(transaction_id)
        if chosen is None:
            raise ValueError("only an offered purchase can be selected")
        self._ensure_in_database(chosen)
        updated = replace(state, current_transaction=chosen.transaction)
        self._calls[session_id] = updated
        _telemetry("web_chat.transaction.option_selected", call_id=session_id)
        result = self.resolve_transaction_candidate(session_id, confirmed=True)
        self._options.pop(session_id, None)
        return result

    def reject_options(self, session_id: str) -> OptionsResult:
        """None of the offered purchases matches: exclude them and ask for one more detail."""

        state = self.get(session_id)
        if state.stage is not VoiceCallStage.CONFIRM_TRANSACTION:
            raise ValueError("there are no options to reject")
        rejected = (
            *state.rejected_transaction_ids,
            *(item.transaction.transaction_id for item in self.options(session_id)),
        )
        self._options.pop(session_id, None)
        _telemetry("web_chat.transaction.options_rejected", call_id=session_id)
        if state.transaction_guess_attempts >= self.max_transaction_guesses:
            return self._as_options(self._transaction_handoff(state))
        return self._refine(
            state,
            state.transaction_criteria,
            reason="options_rejected",
            rejected_transaction_ids=rejected,
        )

    # ------------------------------------------------------------------ suggested problem

    def suggested_allegation(self, session_id: str) -> str | None:
        """What the data suggests about the selected purchase, for Izzy to propose.

        A purchase flagged by the bank's fraud model suggests an unauthorized charge; another
        purchase at the same merchant for the same amount within three days suggests duplicate
        processing. The customer still has to confirm before anything is classified.
        """

        state = self.get(session_id)
        purchase = self.selected_purchase(session_id)
        if purchase is None or state.identity is None:
            return None
        transaction = purchase.transaction
        if transaction.is_fraud or (transaction.fraud_score or 0.0) >= FRAUD_SCORE_SUGGESTION:
            return "UNAUTHORIZED_CARD"
        if self.duplicate_of(session_id) is not None:
            return "DUPLICATE_PROCESSING"
        return None

    def suggest_problem(self, session_id: str) -> str | None:
        """Compute and remember the suggestion Izzy is about to make (None if none)."""

        suggestion = self.suggested_allegation(session_id)
        if suggestion is None:
            self._suggestions.pop(session_id, None)
        else:
            self._suggestions[session_id] = suggestion
        return suggestion

    def pending_suggestion(self, session_id: str) -> str | None:
        return self._suggestions.get(session_id)

    def clear_suggestion(self, session_id: str) -> None:
        self._suggestions.pop(session_id, None)

    def duplicate_of(self, session_id: str) -> CardTransaction | None:
        state = self.get(session_id)
        selected = self.selected_purchase(session_id)
        if selected is None or state.identity is None:
            return None
        chosen = selected.transaction
        return next(
            (
                other
                for other in self.purchases.list_by_customer(state.identity.customer_id)
                if other.transaction.transaction_id != chosen.transaction_id
                and other.transaction.merchant_name == chosen.merchant_name
                and abs(other.transaction.amount - chosen.amount) < 0.01
                and abs(other.transaction.transaction_date - chosen.transaction_date)
                <= timedelta(days=3)
            ),
            None,
        )

    # ------------------------------------------------------------------ complaint

    def _file_classified_complaint(self, state: VoiceCallState) -> VoiceCallState:
        """Web chat files only after the customer confirms (see `file_complaint`).

        Classification still blocks the card right away for unauthorized-card reports, exactly
        as in calls (`VoiceCallService.classify_dispute`).
        """

        return state

    @staticmethod
    def awaiting_complaint_confirmation(state: VoiceCallState) -> bool:
        return (
            state.stage is VoiceCallStage.DISPUTE_CLASSIFIED
            and state.complaint_filing_status is None
        )

    def file_complaint(self, session_id: str) -> VoiceCallState:
        """The customer confirmed: insert the complaint into PostgreSQL (shown in /complaints)."""

        state = self.get(session_id)
        if not self.awaiting_complaint_confirmation(state):
            raise ValueError("there is no classified dispute awaiting confirmation")
        updated = super()._file_classified_complaint(state)
        self._calls[session_id] = updated
        self.call_interactions.sync(updated)
        return updated

    def decline_complaint(self, session_id: str) -> VoiceCallState:
        """The customer does not want to file: end the chat without a complaint."""

        if not self.awaiting_complaint_confirmation(self.get(session_id)):
            raise ValueError("there is no classified dispute awaiting confirmation")
        return self.cancel(session_id)

    # ------------------------------------------------------------------ controls

    def restart_search(self, session_id: str) -> VoiceCallState:
        """Forget the current search and options; keep the authenticated customer."""

        state = self.get(session_id)
        if state.stage in {
            VoiceCallStage.DISPUTE_CLASSIFIED,
            VoiceCallStage.COMPLETED,
            VoiceCallStage.HANDOFF,
        }:
            return state
        updated = replace(
            state,
            stage=VoiceCallStage.AUTHENTICATED,
            transaction_criteria=CardPurchaseCriteria(),
            transaction_candidates=(),
            rejected_transaction_ids=(),
            requested_transaction_fields=(),
            pending_transaction_detail=None,
            current_transaction=None,
            confirmed_transaction=None,
            dispute_classification=None,
            transaction_guess_attempts=0,
            transaction_search_attempts=0,
            transaction_no_match_attempts=0,
        )
        self._calls[session_id] = updated
        self._options.pop(session_id, None)
        _telemetry("web_chat.search.restarted", call_id=session_id, from_stage=state.stage.value)
        return updated

    def cancel(self, session_id: str) -> VoiceCallState:
        """End the conversation without filing anything new."""

        state = self.get(session_id)
        if state.stage in {VoiceCallStage.COMPLETED, VoiceCallStage.HANDOFF}:
            return state
        updated = replace(state, stage=VoiceCallStage.COMPLETED, current_transaction=None)
        self._calls[session_id] = updated
        self._options.pop(session_id, None)
        self.call_interactions.sync(updated)
        _telemetry("web_chat.session.cancelled", call_id=session_id, from_stage=state.stage.value)
        return updated

    def forget(self, session_id: str) -> None:
        """Release an expired chat after recording its final interaction state."""

        self._options.pop(session_id, None)
        self._suggestions.pop(session_id, None)
        if session_id in self._calls:
            self.finalize(session_id)
            del self._calls[session_id]

    # ------------------------------------------------------------------ helpers

    def _offer(
        self, state: VoiceCallState, purchases: tuple[CardTransaction, ...]
    ) -> OptionsResult:
        replacing = state.stage is VoiceCallStage.CONFIRM_TRANSACTION
        updated = replace(
            state,
            stage=VoiceCallStage.CONFIRM_TRANSACTION,
            transaction_candidates=tuple(item.transaction for item in purchases),
            # A single option can also be confirmed with a plain "yes".
            current_transaction=purchases[0].transaction if len(purchases) == 1 else None,
            transaction_guess_attempts=(
                state.transaction_guess_attempts
                if replacing
                else state.transaction_guess_attempts + 1
            ),
            pending_transaction_detail=None,
        )
        self._calls[state.call_id] = updated
        self._options[state.call_id] = purchases
        _telemetry(
            "web_chat.transaction.options_offered",
            call_id=state.call_id,
            option_count=len(purchases),
            guess_number=updated.transaction_guess_attempts,
            sources=sorted({item.source for item in purchases}),
        )
        return OptionsResult(updated, TransactionSelectionOutcome.CANDIDATE, purchases)

    def _refine(
        self,
        state: VoiceCallState,
        criteria: CardPurchaseCriteria,
        *,
        reason: str,
        rejected_transaction_ids: tuple[str, ...] | None = None,
    ) -> OptionsResult:
        self._options.pop(state.call_id, None)
        return self._as_options(
            self._request_transaction_refinement(
                state,
                criteria,
                reason=reason,
                rejected_transaction_ids=rejected_transaction_ids,
            )
        )

    @staticmethod
    def _as_options(selection: TransactionSelectionResult) -> OptionsResult:
        return OptionsResult(selection.state, selection.outcome)

    def _ensure_in_database(self, purchase: CardTransaction) -> None:
        """Keep the app, chat and voice on one database.

        A purchase found only in the lakehouse is copied into PostgreSQL before it is used, so
        complaints and card blocks always refer to rows the app shows.
        """

        transaction = purchase.transaction
        if self.transaction_records.get_by_id(transaction.transaction_id) is not None:
            return
        if self.products.get_by_id(transaction.product_id) is None:
            raise ValueError("the purchase's card is not in the application database")
        try:
            self.transaction_records.create(transaction)
        except ValueError:
            # Created concurrently by another request: the row now exists, which is the goal.
            if self.transaction_records.get_by_id(transaction.transaction_id) is None:
                raise
        _telemetry("web_chat.transaction.copied_from_lakehouse", call_id=None)


__all__ = [
    "OptionsResult",
    "TransactionSelectionOutcome",
    "WebChatDisputeService",
    "chat_locale",
]
