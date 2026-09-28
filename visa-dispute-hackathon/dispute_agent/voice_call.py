"""Server-owned state for synthetic phone and document authentication."""

from __future__ import annotations

import json
import logging
import secrets
import time
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from .caller_identity import (
    CallerIdentity,
    CallerIdentityStatus,
    VoiceCallerIdentityService,
    calling_code_from_phone,
)
from .language_context import ConversationLocaleContext

LOGGER = logging.getLogger(__name__)


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
    HANDOFF = "handoff"


class VoiceAuthenticationMethod(StrEnum):
    PHONE = "phone"
    DOCUMENT = "document"


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


class VoiceCallService:
    """Keep locale, authentication choices, identity, and DTMF server-owned."""

    def __init__(
        self,
        customers_csv: str | Path,
        *,
        max_document_attempts: int = 3,
    ) -> None:
        started = time.monotonic()
        self.identity = VoiceCallerIdentityService(customers_csv)
        self.max_document_attempts = max_document_attempts
        self._calls: dict[str, VoiceCallState] = {}
        _telemetry(
            "voice.service.initialized",
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            max_document_attempts=max_document_attempts,
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

        updated = replace(
            state,
            stage=VoiceCallStage.NEEDS_AUTH_METHOD,
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
