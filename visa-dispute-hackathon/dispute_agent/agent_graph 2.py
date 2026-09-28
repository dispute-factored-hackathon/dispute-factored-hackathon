"""LangGraph orchestration for the deterministic authentication policy engine."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .authentication import AuthenticationAgent, AuthenticationResult
from .openai_interpreter import OpenAITurnInterpreter


class AuthenticationGraphState(TypedDict, total=False):
    answer: str | None
    phase: str
    result: AuthenticationResult


class LangGraphAuthenticationAgent:
    """Expose the call-center interface while executing each customer turn as a graph."""

    def __init__(self, policy: AuthenticationAgent, interpreter: OpenAITurnInterpreter):
        self.policy = policy
        self.interpreter = interpreter
        builder = StateGraph(AuthenticationGraphState)
        builder.add_node("prepare_turn", self._prepare_turn)
        builder.add_node("apply_policy", self._apply_policy)
        builder.add_node("validate_response", self._validate_response)
        builder.add_edge(START, "prepare_turn")
        builder.add_edge("prepare_turn", "apply_policy")
        builder.add_edge("apply_policy", "validate_response")
        builder.add_edge("validate_response", END)
        self.graph = builder.compile()

    def _prepare_turn(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        phase = "name_confirmation" if self.policy.pending_customer else "name_collection"
        self.interpreter.set_phase(phase)
        return {"phase": phase}

    def _apply_policy(self, state: AuthenticationGraphState) -> AuthenticationGraphState:
        return {"result": self.policy.handle_answer(state.get("answer"))}

    @staticmethod
    def _validate_response(state: AuthenticationGraphState) -> AuthenticationGraphState:
        result = state["result"]
        if not result.message.strip():
            raise RuntimeError("Conversation policy returned an empty customer response")
        return {}

    def start(self) -> AuthenticationResult:
        return self.policy.start()

    def handle_answer(self, answer: str | None) -> AuthenticationResult:
        return self.graph.invoke({"answer": answer})["result"]

    @property
    def language(self) -> str:
        return self.policy.language
