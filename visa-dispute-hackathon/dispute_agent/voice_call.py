"""Server-owned state for synthetic phone and document authentication."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from .caller_identity import CallerIdentity, CallerIdentityStatus, VoiceCallerIdentityService
from .language_context import ConversationLocaleContext


class VoiceCallStage(StrEnum):
    NEEDS_LANGUAGE = "needs_language"
    NEEDS_DOCUMENT = "needs_document"
    AUTHENTICATED = "authenticated"
    HANDOFF = "handoff"


@dataclass(frozen=True)
class VoiceCallState:
    call_id: str
    stage: VoiceCallStage
    locale: ConversationLocaleContext
    identity: CallerIdentity | None = None
    failed_document_attempts: int = 0
    document_digits: str = ""


class VoiceCallService:
    """Keep identity, DTMF, and language preferences authoritative on the server."""

    def __init__(self, customers_csv: str | Path, *, max_document_attempts: int = 3) -> None:
        self.identity = VoiceCallerIdentityService(customers_csv)
        self.max_document_attempts = max_document_attempts
        self._calls: dict[str, VoiceCallState] = {}

    def start(self, mobile_phone: str, *, call_id: str | None = None) -> VoiceCallState:
        result = self.identity.identify_phone(mobile_phone)
        resolved_call_id = call_id or secrets.token_urlsafe(24)
        if result.status is CallerIdentityStatus.AUTHENTICATED:
            assert result.identity is not None
            locale = ConversationLocaleContext.from_customer_record(
                country=result.identity.country,
                detected_accent=result.identity.detected_accent,
            )
            state = VoiceCallState(
                resolved_call_id, VoiceCallStage.AUTHENTICATED, locale, result.identity
            )
        else:
            locale = ConversationLocaleContext.from_calling_code(result.country_code)
            state = VoiceCallState(resolved_call_id, VoiceCallStage.NEEDS_LANGUAGE, locale)
        self._calls[resolved_call_id] = state
        return state

    def choose_language(
        self, call_id: str, *, language: str, accent: str | None = None
    ) -> VoiceCallState:
        state = self.get(call_id)
        locale = ConversationLocaleContext.explicit_choice(language, accent)
        stage = VoiceCallStage.AUTHENTICATED if state.identity else VoiceCallStage.NEEDS_DOCUMENT
        updated = replace(state, stage=stage, locale=locale)
        self._calls[call_id] = updated
        return updated

    def receive_dtmf(self, call_id: str, key: str) -> tuple[VoiceCallState, bool]:
        """Consume a DTMF key and return state plus whether a spoken response is needed."""

        state = self.get(call_id)
        if state.stage is not VoiceCallStage.NEEDS_DOCUMENT:
            return state, False
        if len(key) != 1 or key not in "0123456789*#":
            raise ValueError("DTMF key must be one of 0-9, *, or #")
        if key == "*":
            updated = replace(state, document_digits="")
            should_respond = True
        elif key == "#":
            if not state.document_digits:
                return state, True
            return self._authenticate_document(state), True
        else:
            if len(state.document_digits) >= 24:
                raise ValueError("document entry is too long")
            updated = replace(state, document_digits=f"{state.document_digits}{key}")
            should_respond = False
        self._calls[call_id] = updated
        return updated, should_respond

    def _authenticate_document(self, state: VoiceCallState) -> VoiceCallState:
        result = self.identity.identify_document(state.document_digits)
        if result.status is CallerIdentityStatus.AUTHENTICATED:
            updated = replace(
                state,
                stage=VoiceCallStage.AUTHENTICATED,
                identity=result.identity,
                document_digits="",
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
                failed_document_attempts=attempts,
                document_digits="",
            )
        self._calls[state.call_id] = updated
        return updated

    def get(self, call_id: str) -> VoiceCallState:
        try:
            return self._calls[call_id]
        except KeyError as error:
            raise ValueError("voice call does not exist") from error
