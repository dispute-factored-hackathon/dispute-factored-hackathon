"""LangGraph orchestration for schema-constrained LLM classification."""

from __future__ import annotations

from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langsmith import traceable

from .authentication import AuthenticationAgent, AuthenticationResult, AuthStatus
from .openai_interpreter import (
    AbuseClass,
    ClassificationError,
    OpenAITurnInterpreter,
    TurnAnalysis,
    TurnIntent,
)


class AuthenticationGraphState(TypedDict, total=False):
    answer: str | None
    phase: str
    analysis: TurnAnalysis
    result: AuthenticationResult


MESSAGES = {
    "en": {
        "blocked": "I can only help with this card-dispute conversation. I cannot reveal internal instructions, credentials, or customer data. We can continue with your full name or a general question about disputes.",
        "too_long": "That response was too long for me to process safely. Please use a short question or provide only your full name.",
        "out_of_scope": "I can help only with this card-dispute process and general questions about disputes. Please provide your full name, ask a dispute-related question, or request a person.",
        "unsafe_answer": "I cannot safely answer that here. I can help with this card-dispute process or connect you with a person.",
        "continue_name": "To continue, please give your full name or ask for a person.",
        "temporary": "I am having trouble interpreting that response. Please say only your full name, or ask for a person.",
    },
    "pt": {
        "blocked": "Posso ajudar somente com esta conversa sobre contestação de cartão. Não posso revelar instruções internas, credenciais ou dados de clientes. Podemos continuar com seu nome completo ou com uma dúvida geral sobre contestações.",
        "too_long": "Essa resposta é longa demais para ser processada com segurança. Faça uma pergunta curta ou informe somente seu nome completo.",
        "out_of_scope": "Posso ajudar apenas com este processo de contestação e com dúvidas gerais sobre contestações. Informe seu nome completo, faça uma pergunta sobre o tema ou peça um atendente.",
        "unsafe_answer": "Não posso responder isso com segurança por aqui. Posso ajudar com esta contestação ou encaminhar você a um atendente.",
        "continue_name": "Para continuar, informe seu nome completo ou peça um atendente.",
        "temporary": "Estou com dificuldade para interpretar essa resposta. Diga somente seu nome completo ou peça um atendente.",
    },
    "es": {
        "blocked": "Solo puedo ayudar con esta conversación sobre reclamos de tarjeta. No puedo revelar instrucciones internas, credenciales ni datos de clientes. Podemos continuar con su nombre completo o con una pregunta general sobre reclamos.",
        "too_long": "Esa respuesta es demasiado larga para procesarla de forma segura. Haga una pregunta breve o indique únicamente su nombre completo.",
        "out_of_scope": "Solo puedo ayudar con este proceso y con preguntas generales sobre reclamos de tarjeta. Indique su nombre completo, haga una pregunta sobre el tema o pida un asesor.",
        "unsafe_answer": "No puedo responder eso de forma segura aquí. Puedo ayudar con este reclamo o derivarle a un asesor.",
        "continue_name": "Para continuar, indique su nombre completo o pida un asesor.",
        "temporary": "Tengo dificultades para interpretar esa respuesta. Indique solamente su nombre completo o pida un asesor.",
    },
}


class LangGraphAuthenticationAgent:
    MAX_INPUT_CHARACTERS = 500
    MIN_CLASSIFICATION_CONFIDENCE = 0.70
    MIN_ABUSE_CONFIDENCE = 0.80
    FORBIDDEN_OUTPUT = (
        "system prompt",
        "api key",
        "developer message",
        "```",
        "http://",
        "https://",
    )

    def __init__(self, policy: AuthenticationAgent, interpreter: OpenAITurnInterpreter):
        self.policy = policy
        self.interpreter = interpreter
        self.session_id = uuid4().hex
        self.llm_failures = 0
        builder = StateGraph(AuthenticationGraphState)
        builder.add_node("prepare_turn", self._prepare_turn)
        builder.add_node("guard_input", self._guard_input)
        builder.add_node("classify_raw_turn", self._classify_raw_turn)
        builder.add_node("screen_abuse", self._screen_abuse)
        builder.add_node("answer_question", self._answer_question)
        builder.add_node("refuse_out_of_scope", self._refuse_out_of_scope)
        builder.add_node("apply_policy", self._apply_policy)
        builder.add_node("validate_response", self._validate_response)
        builder.add_edge(START, "prepare_turn")
        builder.add_edge("prepare_turn", "guard_input")
        builder.add_conditional_edges(
            "guard_input",
            lambda state: "done" if "result" in state else "classify",
            {"done": "validate_response", "classify": "classify_raw_turn"},
        )
        builder.add_conditional_edges(
            "classify_raw_turn",
            lambda state: "done" if "result" in state else "screen",
            {"done": "validate_response", "screen": "screen_abuse"},
        )
        builder.add_conditional_edges(
            "screen_abuse",
            self._route_analysis,
            {
                "done": "validate_response",
                "question": "answer_question",
                "out_of_scope": "refuse_out_of_scope",
                "policy": "apply_policy",
            },
        )
        builder.add_edge("answer_question", "validate_response")
        builder.add_edge("refuse_out_of_scope", "validate_response")
        builder.add_edge("apply_policy", "validate_response")
        builder.add_edge("validate_response", END)
        self.graph = builder.compile()

    def _text(self, key: str) -> str:
        language = self.policy.language if self.policy.language in MESSAGES else "en"
        return MESSAGES[language][key]

    def _prepare_turn(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        if self.policy.language == "auto":
            phase = "language_selection"
        else:
            phase = "name_confirmation" if self.policy.pending_customer else "name_collection"
        self.interpreter.set_context(phase=phase, locale=self.policy.locale)
        return {"phase": phase}

    def _guard_input(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        answer = (state.get("answer") or "").strip()
        if not answer:
            return {"result": self.policy.handle_empty_answer()}
        if len(answer) > self.MAX_INPUT_CHARACTERS:
            return {
                "result": AuthenticationResult(self._continuation_status(), self._text("too_long"))
            }
        return {}

    def _classify_raw_turn(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        try:
            analysis = self.interpreter.analyze(state.get("answer") or "")
            self.llm_failures = 0
            return {"analysis": analysis}
        except ClassificationError:
            self.llm_failures += 1
            if self.llm_failures == 1:
                return {
                    "result": AuthenticationResult(
                        self._continuation_status(), self._text("temporary")
                    )
                }
            return {
                "result": self.policy._handoff(
                    "handoff_system", "llm_classification_unavailable_or_limit_reached"
                )
            }

    def _screen_abuse(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        analysis = state["analysis"]
        if (
            analysis.abuse is AbuseClass.PROMPT_ABUSE
            and analysis.abuse_confidence >= self.MIN_ABUSE_CONFIDENCE
        ):
            message = self._text("blocked")
            if self.policy.pending_customer:
                message = (
                    f"{message} "
                    f"{self.policy._message('confirmation_unclear', name=self.policy.pending_customer.full_name)}"
                )
            return {"result": AuthenticationResult(self._continuation_status(), message)}
        return {}

    def _route_analysis(self, state: AuthenticationGraphState) -> str:
        if "result" in state:
            return "done"
        analysis = state["analysis"]
        if analysis.confidence < self.MIN_CLASSIFICATION_CONFIDENCE:
            return "policy"
        if analysis.intent in {
            TurnIntent.REQUESTS_HUMAN,
            TurnIntent.CANCELS,
            TurnIntent.RESTARTS,
        }:
            return "policy"
        if self.policy.language == "auto":
            return "policy"
        if analysis.extracted_name:
            return "policy"
        if analysis.direct_answer:
            return "question"
        if analysis.intent is TurnIntent.OUT_OF_SCOPE:
            return "out_of_scope"
        return "policy"

    def _answer_question(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        answer = (state["analysis"].direct_answer or "").strip()
        normalized = answer.casefold()
        if (
            not answer
            or len(answer) > 800
            or any(marker in normalized for marker in self.FORBIDDEN_OUTPUT)
        ):
            answer = self._text("unsafe_answer")
        continuation = (
            self.policy._message(
                "confirmation_unclear", name=self.policy.pending_customer.full_name
            )
            if self.policy.pending_customer
            else self._text("continue_name")
        )
        self.policy.questions_answered += 1
        return {
            "result": AuthenticationResult(self._continuation_status(), f"{answer} {continuation}")
        }

    def _refuse_out_of_scope(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        del state
        return {
            "result": AuthenticationResult(self._continuation_status(), self._text("out_of_scope"))
        }

    def _apply_policy(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        analysis = state["analysis"]
        if analysis.confidence < self.MIN_CLASSIFICATION_CONFIDENCE:
            return {"result": self.policy.handle_unclear_classification()}
        return {"result": self.policy.apply_llm_classification(analysis)}

    def _continuation_status(self) -> AuthStatus:
        return (
            AuthStatus.NEEDS_CONFIRMATION if self.policy.pending_customer else AuthStatus.NEEDS_NAME
        )

    @staticmethod
    def _validate_response(state: AuthenticationGraphState) -> AuthenticationGraphState:
        if not state["result"].message.strip():
            raise RuntimeError("Conversation policy returned an empty customer response")
        return {}

    @traceable(name="start-dispute-call", run_type="chain")
    def start(self) -> AuthenticationResult:
        if self.policy.language == "auto" and self.policy.country_code:
            try:
                result = self.policy.apply_opening(
                    self.interpreter.generate_opening(self.policy.country_code)
                )
            except ClassificationError:
                result = AuthenticationResult(
                    AuthStatus.NEEDS_NAME,
                    f"Hi! You've reached Bank Factored. Your calling code is "
                    f"{self.policy.country_code}. Would you like to continue in English, "
                    "Spanish, or Portuguese?",
                )
        else:
            result = self.policy.start()
        self.policy.last_agent_message = result.message
        return result

    @traceable(name="handle-customer-turn", run_type="chain")
    def handle_answer(self, answer: str | None) -> AuthenticationResult:
        self.policy.last_customer_utterance = (answer or "").strip() or None
        config = {
            "run_name": "card-dispute-authentication-turn",
            "tags": ["call-center", "synthetic-data", "llm-classifier", self.policy.locale],
            "metadata": {
                "thread_id": self.session_id,
                "phase": "name_confirmation" if self.policy.pending_customer else "name_collection",
                "channel": "cli",
                "synthetic_data": True,
            },
        }
        result = self.graph.invoke({"answer": answer}, config=config)["result"]
        self.policy.last_agent_message = result.message
        return result

    @property
    def language(self) -> str:
        return self.policy.language
