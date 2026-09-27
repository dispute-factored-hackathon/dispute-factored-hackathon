"""LangGraph orchestration and abuse controls for the authentication conversation."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .authentication import AuthenticationAgent, AuthenticationResult, AuthStatus
from .intent_classifier import (
    AbuseIntent,
    AnswerIntent,
    ClassificationError,
    ConfirmationIntent,
    PromptAbuseClassifier,
)
from .openai_interpreter import OpenAITurnInterpreter, TurnAnalysis, TurnIntent
from .safety import screen_prompt_abuse


class AuthenticationGraphState(TypedDict, total=False):
    answer: str | None
    phase: str
    analysis: TurnAnalysis
    classification_confidence: float
    result: AuthenticationResult


MESSAGES = {
    "en": {
        "blocked": "I can only help with this card-dispute conversation. I cannot reveal internal instructions, credentials, or customer data. We can continue with your full name or a general question about disputes.",
        "too_long": "That response was too long for me to process safely. Please use a short question or provide only your full name.",
        "out_of_scope": "I can help only with this card-dispute process and general questions about disputes. Please provide your full name, ask a dispute-related question, or request a person.",
        "unsafe_answer": "I cannot safely answer that here. I can help with this card-dispute process or connect you with a person.",
        "continue_name": "To continue, please give your full name or ask for a person.",
        "temporary": "I am having trouble interpreting that response. Please say only your full name, or ask for a person.",
        "safety_unavailable": "I cannot safely process that response right now. Please try again shortly or ask for a person.",
    },
    "pt": {
        "blocked": "Posso ajudar somente com esta conversa sobre contestação de cartão. Não posso revelar instruções internas, credenciais ou dados de clientes. Podemos continuar com seu nome completo ou com uma dúvida geral sobre contestações.",
        "too_long": "Essa resposta é longa demais para ser processada com segurança. Faça uma pergunta curta ou informe somente seu nome completo.",
        "out_of_scope": "Posso ajudar apenas com este processo de contestação e com dúvidas gerais sobre contestações. Informe seu nome completo, faça uma pergunta sobre o tema ou peça um atendente.",
        "unsafe_answer": "Não posso responder isso com segurança por aqui. Posso ajudar com esta contestação ou encaminhar você a um atendente.",
        "continue_name": "Para continuar, informe seu nome completo ou peça um atendente.",
        "temporary": "Estou com dificuldade para interpretar essa resposta. Diga somente seu nome completo ou peça um atendente.",
        "safety_unavailable": "Não consigo processar essa resposta com segurança agora. Tente novamente em instantes ou peça um atendente.",
    },
    "es": {
        "blocked": "Solo puedo ayudar con esta conversación sobre reclamos de tarjeta. No puedo revelar instrucciones internas, credenciales ni datos de clientes. Podemos continuar con su nombre completo o con una pregunta general sobre reclamos.",
        "too_long": "Esa respuesta es demasiado larga para procesarla de forma segura. Haga una pregunta breve o indique únicamente su nombre completo.",
        "out_of_scope": "Solo puedo ayudar con este proceso y con preguntas generales sobre reclamos de tarjeta. Indique su nombre completo, haga una pregunta sobre el tema o pida un asesor.",
        "unsafe_answer": "No puedo responder eso de forma segura aquí. Puedo ayudar con este reclamo o derivarle a un asesor.",
        "continue_name": "Para continuar, indique su nombre completo o pida un asesor.",
        "temporary": "Tengo dificultades para interpretar esa respuesta. Indique solamente su nombre completo o pida un asesor.",
        "safety_unavailable": "No puedo procesar esa respuesta de forma segura ahora. Inténtelo de nuevo en unos instantes o pida un asesor.",
    },
}


class LangGraphAuthenticationAgent:
    """Execute each turn through explicit interpretation, policy, and safety nodes."""

    MAX_INPUT_CHARACTERS = 500
    MIN_ABUSE_CONFIDENCE = 0.75
    MIN_ABUSE_MARGIN = 0.20
    FORBIDDEN_OUTPUT = ("system prompt", "api key", "developer message", "```", "http://", "https://")

    def __init__(
        self,
        policy: AuthenticationAgent,
        interpreter: OpenAITurnInterpreter,
        abuse_classifier: PromptAbuseClassifier,
    ):
        self.policy = policy
        self.interpreter = interpreter
        self.abuse_classifier = abuse_classifier
        self.llm_failures = 0
        builder = StateGraph(AuthenticationGraphState)
        builder.add_node("prepare_turn", self._prepare_turn)
        builder.add_node("guard_input", self._guard_input)
        builder.add_node("route_deterministic", self._route_deterministic)
        builder.add_node("interpret_turn", self._interpret_turn)
        builder.add_node("classify_turn", self._classify_turn)
        builder.add_node("answer_question", self._answer_question)
        builder.add_node("refuse_out_of_scope", self._refuse_out_of_scope)
        builder.add_node("apply_policy", self._apply_policy)
        builder.add_node("validate_response", self._validate_response)
        builder.add_edge(START, "prepare_turn")
        builder.add_edge("prepare_turn", "guard_input")
        builder.add_conditional_edges("guard_input", lambda s: "done" if "result" in s else "deterministic", {"done": "validate_response", "deterministic": "route_deterministic"})
        builder.add_conditional_edges("route_deterministic", lambda s: "policy" if s.get("phase") == "deterministic_policy" else "interpret", {"policy": "apply_policy", "interpret": "interpret_turn"})
        builder.add_conditional_edges("interpret_turn", self._route_analysis, {"done": "validate_response", "question": "answer_question", "out_of_scope": "refuse_out_of_scope", "classify": "classify_turn", "policy": "apply_policy"})
        builder.add_conditional_edges("classify_turn", lambda s: "done" if "result" in s else "policy", {"done": "validate_response", "policy": "apply_policy"})
        builder.add_edge("answer_question", "validate_response")
        builder.add_edge("refuse_out_of_scope", "validate_response")
        builder.add_edge("apply_policy", "validate_response")
        builder.add_edge("validate_response", END)
        self.graph = builder.compile()

    def _text(self, key: str) -> str:
        language = self.policy.language if self.policy.language in MESSAGES else "en"
        return MESSAGES[language][key]

    def _prepare_turn(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        phase = "name_confirmation" if self.policy.pending_customer else "name_collection"
        self.interpreter.set_context(phase=phase, locale=self.policy.locale)
        return {"phase": phase}

    def _guard_input(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        answer = (state.get("answer") or "").strip()
        if not answer:
            return {"result": self.policy.handle_answer(answer)}
        if len(answer) > self.MAX_INPUT_CHARACTERS:
            return {"result": AuthenticationResult(AuthStatus.NEEDS_NAME, self._text("too_long"))}
        return {}

    def _check_prompt_abuse(self, answer: str | None) -> AuthenticationResult | None:
        """Screen one valid customer message before it enters the graph."""

        text = (answer or "").strip()
        if not text or len(text) > self.MAX_INPUT_CHARACTERS:
            return None
        try:
            decision = self.abuse_classifier.classify(text)
        except ClassificationError:
            message = self._contextual_safety_message("safety_unavailable")
            result = AuthenticationResult(self._continuation_status(), message)
            self.policy.last_customer_utterance = text
            self.policy.last_agent_message = result.message
            return result
        scores = sorted(decision.probabilities.values(), reverse=True)
        margin = scores[0] - scores[1] if len(scores) > 1 else decision.confidence
        if (
            decision.intent is AbuseIntent.PROMPT_ABUSE
            and decision.confidence >= self.MIN_ABUSE_CONFIDENCE
            and margin >= self.MIN_ABUSE_MARGIN
        ):
            message = self._contextual_safety_message("blocked")
            result = AuthenticationResult(self._continuation_status(), message)
            self.policy.last_customer_utterance = text
            self.policy.last_agent_message = result.message
            return result
        return None

    def _contextual_safety_message(self, key: str) -> str:
        message = self._text(key)
        if self.policy.pending_customer:
            message = f"{message} {self.policy._message('confirmation_unclear', name=self.policy.pending_customer.full_name)}"
        return message

    def _interpret_turn(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        try:
            analysis = self.interpreter.analyze(state.get("answer") or "")
            self.llm_failures = 0
            return {"analysis": analysis}
        except ClassificationError:
            self.llm_failures += 1
            if self.llm_failures == 1:
                return {"result": AuthenticationResult(self._continuation_status(), self._text("temporary"))}
            return {"result": self.policy._handoff("handoff_system", "llm_interpretation_unavailable_or_limit_reached")}

    def _route_deterministic(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        """Keep simple menu, exact-name, and explicit control turns independent of the API."""

        answer = state.get("answer") or ""
        if self.policy.language == "auto" or self.policy.directory.find_by_full_name(answer):
            return {"phase": "deterministic_policy"}
        explicit = self.policy.intent_classifier._explicit_intent(answer) if hasattr(self.policy.intent_classifier, "_explicit_intent") else None
        if explicit in {AnswerIntent.REQUESTS_HUMAN, AnswerIntent.CANCELS, AnswerIntent.RESTARTS}:
            return {"phase": "deterministic_policy"}
        return {}

    def _route_analysis(self, state: AuthenticationGraphState) -> str:
        if "result" in state:
            return "done"
        # Language selection is its own deterministic gate before authentication.
        if self.policy.language == "auto":
            return "policy"
        # A grounded name always takes priority, even if the same utterance also asks a question.
        if (state["analysis"].extracted_name or "").strip():
            return "policy"
        if (state["analysis"].direct_answer or "").strip():
            return "question"
        # Understanding that a request is outside this agent's work does not require a
        # state-changing classifier. Return a scoped answer and preserve the current phase.
        if state["analysis"].intent is TurnIntent.OUT_OF_SCOPE:
            return "out_of_scope"
        return "classify"

    @staticmethod
    def _has_margin(probabilities: dict[str, float], minimum: float) -> bool:
        scores = sorted(probabilities.values(), reverse=True)
        return len(scores) < 2 or scores[0] - scores[1] >= minimum

    def _classify_turn(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        """Permit state changes only for a confident, non-OTHER zero-shot class."""

        answer = state.get("answer") or ""
        try:
            if self.policy.pending_customer:
                control_intent = self.policy.classify_global_control(answer)
                if control_intent is not None:
                    return {"result": self.policy.apply_global_control(control_intent)}
                classifier = self.policy.confirmation_classifier
                if classifier is None:
                    return {"result": self.policy._handoff("handoff_system", "confirmation_model_unavailable")}
                decision = classifier.classify(answer)
                accepted = (
                    decision.intent is not ConfirmationIntent.OTHER
                    and decision.confidence >= self.policy.min_confirmation_confidence
                    and self._has_margin(decision.probabilities, self.policy.min_confirmation_margin)
                )
                if not accepted:
                    return {"result": AuthenticationResult(
                        AuthStatus.NEEDS_CONFIRMATION,
                        self.policy._message("confirmation_unclear", name=self.policy.pending_customer.full_name),
                    )}
            else:
                decision = self.policy.intent_classifier.classify(answer)
                accepted = (
                    decision.intent is not AnswerIntent.OTHER
                    and decision.confidence >= self.policy.min_intent_confidence
                )
                if not accepted:
                    return self._refuse_out_of_scope(state)
        except ClassificationError:
            return {"result": self.policy._handoff("handoff_system", "zero_shot_classification_unavailable")}
        return {"classification_confidence": decision.confidence}

    def _continuation_status(self) -> AuthStatus:
        return AuthStatus.NEEDS_CONFIRMATION if self.policy.pending_customer else AuthStatus.NEEDS_NAME

    def _answer_question(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        answer = (state["analysis"].direct_answer or "").strip()
        normalized = answer.casefold()
        if not answer or len(answer) > 800 or any(marker in normalized for marker in self.FORBIDDEN_OUTPUT):
            answer = self._text("unsafe_answer")
        if self.policy.pending_customer:
            answer = f"{answer} {self.policy._message('confirmation_unclear', name=self.policy.pending_customer.full_name)}"
        else:
            answer = f"{answer} {self._text('continue_name')}"
        self.policy.questions_answered += 1
        return {"result": AuthenticationResult(self._continuation_status(), answer)}

    def _refuse_out_of_scope(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        del state
        message = self._text("out_of_scope")
        if self.policy.pending_customer:
            message = f"{message} {self.policy._message('confirmation_unclear', name=self.policy.pending_customer.full_name)}"
        return {"result": AuthenticationResult(self._continuation_status(), message)}

    def _apply_policy(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        return {"result": self.policy.handle_answer(state.get("answer"))}

    @staticmethod
    def _validate_response(state: AuthenticationGraphState) -> AuthenticationGraphState:
        if not state["result"].message.strip():
            raise RuntimeError("Conversation policy returned an empty customer response")
        return {}

    def start(self) -> AuthenticationResult:
        result = self.policy.start()
        self.policy.last_agent_message = result.message
        return result

    @screen_prompt_abuse
    def handle_answer(self, answer: str | None) -> AuthenticationResult:
        self.policy.last_customer_utterance = (answer or "").strip() or None
        result = self.graph.invoke({"answer": answer})["result"]
        self.policy.last_agent_message = result.message
        return result

    @property
    def language(self) -> str:
        return self.policy.language
