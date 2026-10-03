"""Web chat entry points on top of the voice dispute workflow.

`WebChatDisputeService` reuses every `VoiceCallService` stage after authentication (transaction
search and confirmation, Visa classification, card blocking, complaint filing, CSAT, handoff). It
only adds what the web needs and leaves the call behaviour untouched:

* the customer is already authenticated by the web session, so a chat starts at AUTHENTICATED
  without asking for a phone number or document;
* a transaction chosen in the web app can be proposed directly for confirmation;
* interactions and complaints are recorded with the Web Chat channel.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from webapp.backend.models.customer import Customer
from webapp.backend.repositories.interfaces import (
    CustomerRepository,
    Repositories,
    TransactionRepository,
)
from webapp.backend.services.call_interactions import WEB_CHAT_CHANNEL, CallInteractionService
from webapp.backend.services.complaint_filing import ComplaintFilingService

from ..caller_identity import VoiceCallerIdentityService
from ..language_context import ConversationLocaleContext
from ..transaction_search import TransactionSearchCriteria
from ..voice_call import (
    TransactionSelectionOutcome,
    TransactionSelectionResult,
    VoiceCallService,
    VoiceCallStage,
    VoiceCallState,
    _telemetry,
    voice_repository_arguments,
)

WEB_SESSION_ASSURANCE = "DEMO_ONLY_WEB_SESSION"
SUPPORTED_LANGUAGES = {"en", "pt", "es"}


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


class WebChatDisputeService(VoiceCallService):
    """The voice dispute workflow, entered from an authenticated web session."""

    def __init__(
        self,
        customers: CustomerRepository,
        transactions: TransactionRepository,
        **repository_arguments: Any,
    ) -> None:
        super().__init__(customers, **repository_arguments)
        self.transaction_records = transactions
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
    def from_repositories(cls, repositories: Repositories) -> WebChatDisputeService:
        return cls(
            repositories.customers,
            repositories.transactions,
            **voice_repository_arguments(repositories),
        )

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

    def propose_known_transaction(
        self, session_id: str, transaction_id: str
    ) -> TransactionSelectionResult | None:
        """Ask the customer to confirm a transaction they opened in the web app.

        Returns None, without revealing whether the id exists, unless the transaction belongs to
        the authenticated customer.
        """

        state = self.get(session_id)
        assert state.identity is not None
        if state.stage is not VoiceCallStage.AUTHENTICATED:
            return None
        transaction = self.transaction_records.get_by_id(transaction_id)
        if transaction is None or transaction.customer_id != state.identity.customer_id:
            _telemetry("web_chat.transaction_context.ignored", call_id=session_id)
            return None
        _telemetry("web_chat.transaction_context.accepted", call_id=session_id)
        return self._propose_transaction(
            replace(state, transaction_candidates=(transaction,)),
            transaction,
            result_count=1,
        )

    def restart_search(self, session_id: str) -> VoiceCallState:
        """Forget the current search and candidate; keep the authenticated customer."""

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
            transaction_criteria=TransactionSearchCriteria(),
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
        _telemetry("web_chat.search.restarted", call_id=session_id, from_stage=state.stage.value)
        return updated

    def cancel(self, session_id: str) -> VoiceCallState:
        """End the conversation without filing anything new."""

        state = self.get(session_id)
        if state.stage in {VoiceCallStage.COMPLETED, VoiceCallStage.HANDOFF}:
            return state
        updated = replace(state, stage=VoiceCallStage.COMPLETED, current_transaction=None)
        self._calls[session_id] = updated
        self.call_interactions.sync(updated)
        _telemetry("web_chat.session.cancelled", call_id=session_id, from_stage=state.stage.value)
        return updated

    def forget(self, session_id: str) -> None:
        """Release an expired chat after recording its final interaction state."""

        if session_id in self._calls:
            self.finalize(session_id)
            del self._calls[session_id]


__all__ = [
    "TransactionSelectionOutcome",
    "WebChatDisputeService",
    "chat_locale",
]
