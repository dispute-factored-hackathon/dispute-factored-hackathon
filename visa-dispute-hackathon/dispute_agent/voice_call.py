"""Server-owned state for phone and document voice authentication."""

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
    """Keep identity and spoken preferences authoritative on the server."""

    def __init__(self, customers_csv: str | Path, *, max_document_attempts: int = 3) -> None:
        self.identity = VoiceCallerIdentityService(customers_csv)
        self.max_document_attempts = max_document_attempts
        self._calls: dict[str, VoiceCallState] = {}

    def start(self, mobile_phone: str) -> VoiceCallState:
        result = self.identity.identify_phone(mobile_phone)
        call_id = secrets.token_urlsafe(24)
        if result.status is CallerIdentityStatus.AUTHENTICATED:
            assert result.identity is not None
            locale = ConversationLocaleContext.from_customer_record(
                country=result.identity.country,
                detected_accent=result.identity.detected_accent,
            )
            state = VoiceCallState(call_id, VoiceCallStage.AUTHENTICATED, locale, result.identity)
        else:
            country_by_code = {
                "+55": "Brazil",
                "+57": "Colombia",
                "+52": "Mexico",
                "+54": "Argentina",
                "+351": "Portugal",
                "+34": "Spain",
            }
            country = country_by_code.get(result.country_code)
            locale = ConversationLocaleContext.from_gui_record(
                country=country,
                preferred_language=None,
                locale=None,
            )
            state = VoiceCallState(call_id, VoiceCallStage.NEEDS_LANGUAGE, locale)
        self._calls[call_id] = state
        return state

    def choose_language(
        self, call_id: str, *, language: str, accent: str | None = None
    ) -> VoiceCallState:
        state = self.get(call_id)
        locale = ConversationLocaleContext.explicit_choice(language, accent)
        next_stage = (
            VoiceCallStage.AUTHENTICATED
            if state.identity is not None
            else VoiceCallStage.NEEDS_DOCUMENT
        )
        updated = replace(state, stage=next_stage, locale=locale)
        self._calls[call_id] = updated
        return updated

    def authenticate_document(self, call_id: str, document_number: str) -> VoiceCallState:
        state = self.get(call_id)
        if state.stage is VoiceCallStage.NEEDS_LANGUAGE:
            raise ValueError("preferred language must be confirmed before document authentication")
        result = self.identity.identify_document(document_number)
        if result.status is CallerIdentityStatus.AUTHENTICATED:
            updated = replace(
                state,
                stage=VoiceCallStage.AUTHENTICATED,
                identity=result.identity,
                document_digits="",
            )
        else:
            attempts = state.failed_document_attempts + 1
            if attempts >= self.max_document_attempts:
                updated = replace(
                    state,
                    stage=VoiceCallStage.HANDOFF,
                    failed_document_attempts=attempts,
                    document_digits="",
                )
            else:
                updated = replace(
                    state,
                    failed_document_attempts=attempts,
                    document_digits="",
                )
        self._calls[call_id] = updated
        return updated

    def receive_dtmf(self, call_id: str, key: str) -> VoiceCallState:
        """Consume one SIP `transport.dtmf.received` event without model access."""

        state = self.get(call_id)
        if state.stage is not VoiceCallStage.NEEDS_DOCUMENT:
            raise ValueError("DTMF document entry is not active")
        if key not in "0123456789*#" or len(key) != 1:
            raise ValueError("DTMF key must be one of 0-9, *, or #")
        if key == "*":
            updated = replace(state, document_digits="")
        elif key == "#":
            if not state.document_digits:
                raise ValueError("enter document digits before pressing #")
            return self.authenticate_document(call_id, state.document_digits)
        else:
            if len(state.document_digits) >= 24:
                raise ValueError("document entry is too long")
            updated = replace(state, document_digits=f"{state.document_digits}{key}")
        self._calls[call_id] = updated
        return updated

    def get(self, call_id: str) -> VoiceCallState:
        try:
            return self._calls[call_id]
        except KeyError as error:
            raise ValueError("voice call does not exist") from error
