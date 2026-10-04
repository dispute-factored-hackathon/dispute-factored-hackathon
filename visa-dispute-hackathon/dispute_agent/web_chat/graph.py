"""LangGraph workflow for the Izzy web chat.

One graph invocation handles one typed customer turn:

    guard_input -> interpret -> screen_abuse -> global_controls -> workflow -> compose_reply

* `guard_input` enforces length, empty-message and per-session turn limits, and closes finished
  conversations without calling a model.
* `interpret` uses the shared decision boundary (Jev, then the structured LLM classifier).
* `screen_abuse` blocks prompt abuse on this single ingress before any branch runs.
* `global_controls` applies human, restart and cancel before stage-specific decisions.
* `workflow` applies the decision through `WebChatDisputeService` (the voice workflow), only when
  the intent is allowed for the stage and passes the confidence gate.
* `compose_reply` streams the reply. The authoritative state lives in the service; the graph
  state keeps only raw per-turn data and a short history, checkpointed per chat thread.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field, replace
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from webapp.backend.models.card_transaction import CardTransaction
from webapp.backend.models.customer import Customer

from ..dispute_classification import DisputeAllegation
from ..sip_realtime import _guard_extracted_numeric_filters
from ..voice_call import (
    DisputeClassificationOutcome,
    TransactionSelectionOutcome,
    VoiceCallStage,
    VoiceCallState,
)
from .interpreter import (
    ChatIntent,
    ChatTurnInterpretation,
    ChatTurnInterpreter,
    InterpreterUnavailableError,
    TurnDecision,
)
from .replies import (
    DETERMINISTIC_OUTCOMES,
    LANGUAGE_NAMES,
    REPLY_PROMPT,
    format_phone,
    reference_message,
    reply_facts,
    required_tokens,
    selected_transaction_message,
    web_text,
)
from .search import CardPurchaseCriteria, option_payload, typed_date_evidence
from .service import WebChatDisputeService

LOGGER = logging.getLogger(__name__)

MAX_HISTORY_ENTRIES = 8
MAX_REPLY_CHARS = 900
REPLY_NODE = "compose_reply"

SELECTION_OUTCOMES = {
    TransactionSelectionOutcome.NEEDS_CLARIFICATION: "transaction_clarification",
    TransactionSelectionOutcome.NO_MATCH: "transaction_no_match",
    TransactionSelectionOutcome.CANDIDATE: "transaction_options",
    TransactionSelectionOutcome.CONFIRMED: "classification_question",
    TransactionSelectionOutcome.EXHAUSTED: "transaction_handoff",
}
# What to ask again when a turn is unclear or below the confidence gate, per stage.
CLARIFICATION_OUTCOMES = {
    VoiceCallStage.AUTHENTICATED: "transaction_clarification",
    VoiceCallStage.NEEDS_TRANSACTION_DETAILS: "transaction_clarification",
    VoiceCallStage.CONFIRM_TRANSACTION: "options_unclear",
    VoiceCallStage.NEEDS_DISPUTE_CLASSIFICATION: "classification_clarification",
    VoiceCallStage.DISPUTE_CLASSIFIED: "csat_unclear",
}
CLOSED_STAGES = {VoiceCallStage.COMPLETED, VoiceCallStage.HANDOFF}


def _keep_recent(
    existing: list[dict[str, str]] | None, new: list[dict[str, str]] | None
) -> list[dict[str, str]]:
    return [*(existing or []), *(new or [])][-MAX_HISTORY_ENTRIES:]


class ChatGraphState(TypedDict, total=False):
    session_id: str
    message: str
    # Explicit UI actions on the offered purchases (tapping an option or "None of these").
    selected_transaction_id: str | None
    reject_options: bool
    turns: int
    history: Annotated[list[dict[str, str]], _keep_recent]
    intent: str | None
    confidence: float
    prompt_abuse: bool
    decision_source: str | None
    interpretation: dict[str, Any] | None
    jev_arguments: dict[str, Any]
    outcome: str
    reply: str


def _log(event: str, **fields: Any) -> None:
    LOGGER.info(json.dumps({"event": event, **fields}, ensure_ascii=False, default=str))


def _default_reply_model(api_key: str, model: str) -> Any:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        api_key=api_key,
        model=model,
        temperature=0.3,
        max_retries=1,
        timeout=20,
        streaming=True,
    )


class IzzyChatGraph:
    """Builds and runs the per-turn graph over the shared dispute workflow."""

    def __init__(
        self,
        service: WebChatDisputeService,
        interpreter: ChatTurnInterpreter,
        *,
        phone_number: str,
        max_message_chars: int,
        max_turns: int,
        reply_model: Any | None = None,
        reply_model_factory: Callable[[str, str], Any] = _default_reply_model,
        openai_api_key: str | None = None,
        model: str = "gpt-4.1-mini",
    ) -> None:
        self.service = service
        self.interpreter = interpreter
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model
        self.phone_number = phone_number
        self.max_message_chars = max_message_chars
        self.max_turns = max_turns
        self._reply_model = reply_model
        self._reply_model_factory = reply_model_factory
        self.graph = self._build().compile(checkpointer=InMemorySaver())

    def _build(self) -> StateGraph:
        builder = StateGraph(ChatGraphState)
        builder.add_node("guard_input", self.guard_input)
        builder.add_node("interpret", self.interpret)
        builder.add_node("screen_abuse", self.screen_abuse)
        builder.add_node("global_controls", self.global_controls)
        builder.add_node("workflow", self.workflow)
        builder.add_node(REPLY_NODE, self.compose_reply)
        builder.add_edge(START, "guard_input")
        builder.add_conditional_edges("guard_input", self._next_unless_decided("interpret"))
        builder.add_conditional_edges("interpret", self._next_unless_decided("screen_abuse"))
        builder.add_conditional_edges("screen_abuse", self._next_unless_decided("global_controls"))
        builder.add_conditional_edges("global_controls", self._next_unless_decided("workflow"))
        builder.add_edge("workflow", REPLY_NODE)
        builder.add_edge(REPLY_NODE, END)
        return builder

    @staticmethod
    def _next_unless_decided(next_node: str) -> Callable[[ChatGraphState], str]:
        def route(state: ChatGraphState) -> str:
            return REPLY_NODE if state.get("outcome") else next_node

        route.__name__ = f"route_to_{next_node}"
        return route

    # ------------------------------------------------------------------ nodes

    def guard_input(self, state: ChatGraphState) -> dict[str, Any]:
        turns = state.get("turns", 0) + 1
        text = state.get("message", "").strip()
        ui_action = bool(state.get("selected_transaction_id") or state.get("reject_options"))
        workflow_state = self.service.get(state["session_id"])
        outcome = ""
        if workflow_state.stage in CLOSED_STAGES:
            outcome = "conversation_closed"
        elif turns > self.max_turns:
            outcome = "rate_limited"
        elif not text and not ui_action:
            outcome = "empty"
        elif len(text) > self.max_message_chars:
            outcome = "too_long"
        return {"turns": turns, "outcome": outcome, "message": text}

    async def interpret(self, state: ChatGraphState) -> dict[str, Any]:
        workflow_state = self.service.get(state["session_id"])
        if state.get("selected_transaction_id") or state.get("reject_options"):
            # A tap on an offered option is an explicit choice: no model interprets it, and the
            # service still accepts only an option it offered to this customer.
            return {
                "intent": (
                    ChatIntent.SELECT_OPTION.value
                    if state.get("selected_transaction_id")
                    else ChatIntent.DENY_TRANSACTION.value
                ),
                "confidence": 1.0,
                "decision_source": "ui",
                "interpretation": None,
            }
        try:
            decision = await self.interpreter.interpret(
                stage=workflow_state.stage.value,
                message=state["message"],
                language=workflow_state.locale.language,
                candidate=self._candidate_summary(workflow_state),
            )
        except InterpreterUnavailableError as error:
            _log("web_chat.interpret.unavailable", reason=str(error))
            return {"outcome": "unavailable"}
        return {
            "intent": decision.intent.value,
            "confidence": decision.confidence,
            "prompt_abuse": decision.prompt_abuse,
            "decision_source": decision.source,
            "interpretation": (
                decision.interpretation.model_dump(mode="json")
                if decision.interpretation is not None
                else None
            ),
            "jev_arguments": decision.jev_arguments,
        }

    def screen_abuse(self, state: ChatGraphState) -> dict[str, Any]:
        if state.get("prompt_abuse"):
            _log("web_chat.prompt_abuse.blocked", source=state.get("decision_source"))
            return {"outcome": "prompt_abuse"}
        return {}

    def global_controls(self, state: ChatGraphState) -> dict[str, Any]:
        intent = ChatIntent(state["intent"])
        if intent not in {ChatIntent.REQUEST_HUMAN, ChatIntent.RESTART, ChatIntent.CANCEL}:
            return {}
        session_id = state["session_id"]
        workflow_state = self.service.get(session_id)
        if not self.interpreter.passes(self._decision(state), workflow_state.stage.value):
            return {}
        if intent is ChatIntent.REQUEST_HUMAN:
            self.service.request_human(session_id)
            return {"outcome": "handoff"}
        if intent is ChatIntent.RESTART:
            if workflow_state.stage is VoiceCallStage.DISPUTE_CLASSIFIED:
                return {}
            self.service.restart_search(session_id)
            return {"outcome": "restarted"}
        self.service.cancel(session_id)
        return {"outcome": "cancelled"}

    def workflow(self, state: ChatGraphState) -> dict[str, Any]:
        session_id = state["session_id"]
        workflow_state = self.service.get(session_id)
        intent = ChatIntent(state["intent"])
        if intent is ChatIntent.QUESTION:
            return {"outcome": "question"}
        if intent is ChatIntent.OUT_OF_SCOPE:
            return {"outcome": "out_of_scope"}
        clarification = CLARIFICATION_OUTCOMES.get(workflow_state.stage, "conversation_closed")
        if not self.interpreter.passes(self._decision(state), workflow_state.stage.value):
            return {"outcome": clarification}
        try:
            return {"outcome": self._apply(state, workflow_state, intent)}
        except ValueError as error:
            _log(
                "web_chat.workflow.rejected",
                stage=workflow_state.stage.value,
                intent=intent.value,
                error_type=type(error).__name__,
            )
            return {"outcome": clarification}

    async def compose_reply(self, state: ChatGraphState) -> dict[str, Any]:
        session_id = state["session_id"]
        workflow_state = self.service.get(session_id)
        outcome = state.get("outcome") or "question"
        reference = reference_message(workflow_state, outcome, phone=self.phone_number)
        writer = get_stream_writer()
        if outcome == "transaction_options":
            writer(
                {
                    "type": "options",
                    "options": [option_payload(item) for item in self.service.options(session_id)],
                }
            )
        if (
            workflow_state.confirmed_transaction is not None
            and outcome == "classification_question"
        ):
            writer(
                {
                    "type": "selected",
                    "transaction_id": workflow_state.confirmed_transaction.transaction_id,
                }
            )
        reply = reference
        model = None if outcome in DETERMINISTIC_OUTCOMES else self._reply_model_or_none()
        if model is None:
            writer({"type": "delta", "text": reference})
        else:
            facts = reply_facts(
                workflow_state,
                outcome,
                phone=self.phone_number,
                card_last_four=self._card_last_four(workflow_state),
            )
            reply = await self._generate(model, state, workflow_state, facts, reference)
            if not self._valid_reply(reply, facts):
                _log("web_chat.reply.fallback", outcome=outcome)
                reply = reference
                writer({"type": "replace", "text": reference})
        message = state.get("message", "")
        if message:
            self.service.record_transcript_turn(session_id, speaker="customer", text=message)
        self.service.record_transcript_turn(session_id, speaker="agent", text=reply)
        history = [{"role": "izzy", "content": reply}]
        if message:
            history.insert(0, {"role": "customer", "content": message})
        return {"reply": reply, "history": history, "outcome": outcome}

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _decision(state: ChatGraphState) -> TurnDecision:
        return TurnDecision(
            intent=ChatIntent(state["intent"]),
            confidence=float(state.get("confidence", 0.0)),
            prompt_abuse=bool(state.get("prompt_abuse")),
            source=state.get("decision_source") or "llm",
        )

    def _apply(
        self, state: ChatGraphState, workflow_state: VoiceCallState, intent: ChatIntent
    ) -> str:
        session_id = state["session_id"]
        stage = workflow_state.stage
        interpretation = (
            ChatTurnInterpretation.model_validate(state["interpretation"])
            if state.get("interpretation")
            else None
        )
        if intent is ChatIntent.DESCRIBE_TRANSACTION and interpretation is not None:
            return self._search(session_id, workflow_state, interpretation, state["message"])
        if stage is VoiceCallStage.CONFIRM_TRANSACTION:
            options = self.service.options(session_id)
            if intent is ChatIntent.SELECT_OPTION:
                transaction_id = state.get("selected_transaction_id") or self._option_by_number(
                    options, interpretation
                )
                if transaction_id is None:
                    return "options_unclear"
                selection = self.service.select_option(session_id, transaction_id)
                return SELECTION_OUTCOMES[selection.outcome]
            if intent is ChatIntent.CONFIRM_TRANSACTION:
                if len(options) != 1:
                    return "options_unclear"
                selection = self.service.select_option(
                    session_id, options[0].transaction.transaction_id
                )
                return SELECTION_OUTCOMES[selection.outcome]
            if intent is ChatIntent.DENY_TRANSACTION:
                rejected = self.service.reject_options(session_id)
                if (
                    interpretation is not None
                    and rejected.outcome is not TransactionSelectionOutcome.EXHAUSTED
                    and self._criteria(interpretation, state["message"], None).has_any_filter
                ):
                    return self._search(
                        session_id, self.service.get(session_id), interpretation, state["message"]
                    )
                return SELECTION_OUTCOMES[rejected.outcome]
        if stage is VoiceCallStage.NEEDS_DISPUTE_CLASSIFICATION and (
            intent is ChatIntent.REPORT_PROBLEM
        ):
            evidence = self._classification_evidence(state, interpretation)
            result = self.service.classify_dispute(session_id, **evidence)
            return (
                "classification_complete"
                if result.outcome is DisputeClassificationOutcome.CLASSIFIED
                else "classification_clarification"
            )
        if stage is VoiceCallStage.DISPUTE_CLASSIFIED:
            if intent is ChatIntent.CSAT_DECLINE:
                self.service.decline_csat(session_id)
                return "csat_declined"
            rating = self._rating(state, interpretation)
            if intent is ChatIntent.CSAT_RATING and rating is not None:
                self.service.record_csat(session_id, rating=rating)
                return "csat_thanks"
        return CLARIFICATION_OUTCOMES.get(stage, "conversation_closed")

    def _search(
        self,
        session_id: str,
        workflow_state: VoiceCallState,
        interpretation: ChatTurnInterpretation,
        message: str,
    ) -> str:
        criteria = self._criteria(
            interpretation, message, workflow_state.pending_transaction_detail
        )
        result = self.service.search_options(
            session_id,
            criteria,
            clear_filters=interpretation.clear_filters,
            remove_filters=tuple(interpretation.remove_filters),
        )
        return SELECTION_OUTCOMES[result.outcome]

    @staticmethod
    def _criteria(
        interpretation: ChatTurnInterpretation, message: str, expected_field: str | None
    ) -> CardPurchaseCriteria:
        """Validate extracted filters and drop numbers the customer never wrote (as in calls)."""

        criteria = CardPurchaseCriteria.from_mapping(interpretation.search_arguments())
        guarded, dropped = _guard_extracted_numeric_filters(
            criteria, message, expected_field=expected_field
        )
        result = CardPurchaseCriteria.upgrade(guarded, category=criteria.category)
        if {"date_from", "date_to"} & set(dropped) and typed_date_evidence(message):
            # The voice guard needs a number next to a date word; typed years and periods
            # ("in 2025", "yesterday", "last month") are real dates the customer wrote.
            result = replace(result, date_from=criteria.date_from, date_to=criteria.date_to)
            dropped = tuple(name for name in dropped if name not in {"date_from", "date_to"})
        if dropped:
            _log("web_chat.transaction.unsupported_filters_dropped", filters=dropped)
        return result

    @staticmethod
    def _option_by_number(
        options: tuple[CardTransaction, ...], interpretation: ChatTurnInterpretation | None
    ) -> str | None:
        number = interpretation.option_number if interpretation is not None else None
        if isinstance(number, int) and 1 <= number <= len(options):
            return options[number - 1].transaction.transaction_id
        return None

    @staticmethod
    def _classification_evidence(
        state: ChatGraphState, interpretation: ChatTurnInterpretation | None
    ) -> dict[str, Any]:
        jev = state.get("jev_arguments") or {}
        if jev.get("allegation"):
            allegation = str(jev["allegation"])
            environment = jev.get("customer_reported_card_environment")
        elif interpretation is not None and interpretation.allegation:
            allegation = interpretation.allegation
            environment = interpretation.card_environment
        else:
            allegation = DisputeAllegation.INSUFFICIENT_INFO.value
            environment = None
        if environment == "UNKNOWN":
            environment = None
        return {
            "allegation": DisputeAllegation(allegation),
            "customer_denies_authorization": allegation == "UNAUTHORIZED_CARD",
            "customer_reports_duplicate": allegation == "DUPLICATE_PROCESSING",
            "customer_reported_card_environment": environment,
        }

    @staticmethod
    def _rating(state: ChatGraphState, interpretation: ChatTurnInterpretation | None) -> int | None:
        jev_rating = (state.get("jev_arguments") or {}).get("rating")
        rating = (
            jev_rating
            if jev_rating is not None
            else (interpretation.rating if interpretation is not None else None)
        )
        if isinstance(rating, int) and not isinstance(rating, bool) and 1 <= rating <= 5:
            return rating
        return None

    def _candidate_summary(self, workflow_state: VoiceCallState) -> list[dict[str, Any]] | None:
        """The offered purchases, numbered as the customer sees them."""

        options = self.service.options(workflow_state.call_id)
        if not options:
            return None
        return [
            {
                "number": number,
                "merchant": item.transaction.merchant_name,
                "date": item.transaction.transaction_date.date().isoformat(),
                "amount": item.transaction.amount,
                "currency": item.transaction.currency,
                "category": item.transaction.transaction_category,
                "card_last_four": item.card_last_four,
            }
            for number, item in enumerate(options, start=1)
        ]

    def _card_last_four(self, workflow_state: VoiceCallState) -> str | None:
        selected = self.service.selected_purchase(workflow_state.call_id)
        if selected is not None:
            return selected.card_last_four
        transaction = workflow_state.current_transaction or workflow_state.confirmed_transaction
        if transaction is None:
            return None
        product = self.service.products.get_by_id(transaction.product_id)
        return product.product_number[-4:] if product is not None else None

    def _reply_model_or_none(self) -> Any | None:
        if self._reply_model is None:
            if not self.openai_api_key.strip():
                return None
            try:
                self._reply_model = self._reply_model_factory(self.openai_api_key, self.model)
            except Exception as error:
                _log("web_chat.reply_model.unavailable", error_type=type(error).__name__)
                return None
        return self._reply_model

    async def _generate(
        self,
        model: Any,
        state: ChatGraphState,
        workflow_state: VoiceCallState,
        facts: dict[str, Any],
        reference: str,
    ) -> str:
        prompt = REPLY_PROMPT.format(
            language_name=LANGUAGE_NAMES.get(workflow_state.locale.language, "English"),
            facts=json.dumps(facts, ensure_ascii=False),
            reference=reference,
        )
        messages: list[tuple[str, str]] = [("system", prompt)]
        for entry in state.get("history", [])[-6:]:
            messages.append(("ai" if entry["role"] == "izzy" else "human", entry["content"]))
        if state.get("message"):
            messages.append(("human", state["message"]))
        parts: list[str] = []
        try:
            async for chunk in model.astream(
                messages,
                config={"run_name": "izzy_web_chat_reply", "tags": ["channel:web"]},
            ):
                if isinstance(chunk.content, str):
                    parts.append(chunk.content)
        except Exception as error:
            _log("web_chat.reply.failed", error_type=type(error).__name__)
            return ""
        return "".join(parts).strip()

    @staticmethod
    def _valid_reply(reply: str, facts: dict[str, Any]) -> bool:
        if not reply or len(reply) > MAX_REPLY_CHARS:
            return False
        return all(token in reply for token in required_tokens(facts))


# ---------------------------------------------------------------------- sessions


class ChatSessionNotFoundError(LookupError):
    """Unknown, expired, or another customer's chat session (indistinguishable on purpose)."""


@dataclass
class ChatSession:
    session_id: str
    customer_id: str
    last_seen: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass(frozen=True)
class ChatOpening:
    session_id: str
    message: str
    stage: str
    language: str
    transaction_context: bool
    options: tuple[dict[str, Any], ...] = ()
    selected_transaction_id: str | None = None


class IzzyWebChat:
    """Session ownership, expiry and streaming on top of `IzzyChatGraph`."""

    def __init__(
        self,
        service: WebChatDisputeService,
        interpreter: ChatTurnInterpreter,
        *,
        phone_number: str,
        session_ttl_seconds: float,
        max_message_chars: int,
        max_turns: int,
        reply_model: Any | None = None,
        reply_model_factory: Callable[[str, str], Any] = _default_reply_model,
        openai_api_key: str | None = None,
        model: str = "gpt-4.1-mini",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.service = service
        self.phone_number = phone_number
        self.session_ttl_seconds = session_ttl_seconds
        self.chat = IzzyChatGraph(
            service,
            interpreter,
            phone_number=phone_number,
            max_message_chars=max_message_chars,
            max_turns=max_turns,
            reply_model=reply_model,
            reply_model_factory=reply_model_factory,
            openai_api_key=openai_api_key,
            model=model,
        )
        self._clock = clock
        self._sessions: dict[str, ChatSession] = {}

    @property
    def phone_display(self) -> str:
        return format_phone(self.phone_number)

    def _purge_expired(self) -> None:
        now = self._clock()
        for session_id, session in list(self._sessions.items()):
            if now - session.last_seen > self.session_ttl_seconds and not session.lock.locked():
                del self._sessions[session_id]
                self.service.forget(session_id)

    def _owned(self, session_id: str, customer_id: str) -> ChatSession:
        self._purge_expired()
        session = self._sessions.get(session_id)
        if session is None or not secrets.compare_digest(session.customer_id, customer_id):
            raise ChatSessionNotFoundError(session_id)
        session.last_seen = self._clock()
        return session

    def open_session(
        self,
        customer: Customer,
        *,
        locale: str | None = None,
        transaction_id: str | None = None,
    ) -> ChatOpening:
        """Start a chat for the session customer; never asks for the Factored ID again."""

        self._purge_expired()
        session_id = secrets.token_urlsafe(24)
        state = self.service.start_session(session_id, customer, locale=locale)
        language = state.locale.language
        message = web_text(language, "greeting", name=customer.first_name)
        transaction_context = False
        options: tuple[dict[str, Any], ...] = ()
        selected_transaction_id: str | None = None
        if transaction_id:
            # Opening the chat from a purchase is an explicit choice: it is selected directly.
            selected = self.service.select_known_transaction(session_id, transaction_id)
            purchase = self.service.selected_purchase(session_id) if selected else None
            if selected is not None and purchase is not None:
                transaction_context = True
                options = (option_payload(purchase),)
                selected_transaction_id = purchase.transaction.transaction_id
                candidate = selected_transaction_message(selected.state)
                greeting = web_text(language, "greeting_with_transaction", name=customer.first_name)
                message = f"{greeting} {candidate}"
        self._sessions[session_id] = ChatSession(session_id, customer.customer_id, self._clock())
        self.service.record_transcript_turn(session_id, speaker="agent", text=message)
        return ChatOpening(
            session_id=session_id,
            message=message,
            stage=self.service.get(session_id).stage.value,
            language=language,
            transaction_context=transaction_context,
            options=options,
            selected_transaction_id=selected_transaction_id,
        )

    def ensure_owned(self, session_id: str, customer_id: str) -> None:
        self._owned(session_id, customer_id)

    async def stream_turn(
        self,
        session_id: str,
        customer_id: str,
        message: str,
        *,
        selected_transaction_id: str | None = None,
        reject_options: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield `delta`, `replace`, `options`, `selected`, `state`, `done` (or `error`) events."""

        session = self._owned(session_id, customer_id)
        config = {
            "configurable": {"thread_id": session_id},
            "run_name": "izzy_web_chat_turn",
            "tags": ["channel:web", "agent:izzy"],
        }
        turn_input: ChatGraphState = {
            "session_id": session_id,
            "message": message,
            "selected_transaction_id": selected_transaction_id,
            "reject_options": reject_options,
            "intent": None,
            "confidence": 0.0,
            "prompt_abuse": False,
            "decision_source": None,
            "interpretation": None,
            "jev_arguments": {},
            "outcome": "",
            "reply": "",
        }
        async with session.lock:
            try:
                async for part in self.chat.graph.astream(
                    turn_input, config, stream_mode=["messages", "custom"], version="v2"
                ):
                    if part["type"] == "messages":
                        chunk, metadata = part["data"]
                        content = chunk.content
                        if (
                            metadata.get("langgraph_node") == REPLY_NODE
                            and isinstance(content, str)
                            and content
                        ):
                            yield {"event": "delta", "text": content}
                    elif part["type"] == "custom":
                        data = dict(part["data"])
                        yield {"event": data.pop("type"), **data}
            except Exception as error:
                _log("web_chat.turn.failed", error_type=type(error).__name__)
                workflow_state = self.service.get(session_id)
                yield {
                    "event": "error",
                    "text": web_text(
                        workflow_state.locale.language, "unavailable", phone=self.phone_number
                    ),
                }
                return
            snapshot = await self.chat.graph.aget_state({"configurable": {"thread_id": session_id}})
            workflow_state = self.service.get(session_id)
            yield {
                "event": "state",
                "stage": workflow_state.stage.value,
                "outcome": snapshot.values.get("outcome"),
                "complaint_id": workflow_state.complaint_id,
                "closed": workflow_state.stage in CLOSED_STAGES,
            }
            yield {"event": "done"}
