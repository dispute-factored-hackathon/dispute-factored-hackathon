"""Controlled Twilio PSTN handoff for an active SIP call."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from typing import Any

import httpx

from .human_handoff import normalize_e164

_CALL_SID = re.compile(r"^CA[0-9a-fA-F]{32}$")


@dataclass(frozen=True)
class TwilioHandoffCredentials:
    account_sid: str
    api_key_sid: str
    api_key_secret: str
    caller_id: str

    def __post_init__(self) -> None:
        if not self.account_sid.startswith("AC"):
            raise ValueError("Twilio account SID must start with AC")
        if not self.api_key_sid.startswith("SK"):
            raise ValueError("Twilio API key SID must start with SK")
        if not self.api_key_secret:
            raise ValueError("Twilio API key secret is required")
        if normalize_e164(self.caller_id) != self.caller_id:
            raise ValueError("Twilio caller ID must use E.164 format")


class TwilioHandoffError(RuntimeError):
    """Raised when Twilio cannot identify or redirect the active call."""


class TwilioCallHandoff:
    """Replace the active SIP leg with a Twilio-controlled PSTN dial."""

    def __init__(
        self,
        credentials: TwilioHandoffCredentials,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.credentials = credentials
        self._client = httpx.Client(
            auth=(credentials.api_key_sid, credentials.api_key_secret),
            timeout=timeout_seconds,
            transport=transport,
        )

    def transfer(
        self,
        *,
        caller_phone: str,
        target_phone: str,
        call_sid: str | None = None,
    ) -> str:
        """Redirect the matching active call and return its Twilio Call SID."""

        caller = normalize_e164(caller_phone)
        target = normalize_e164(target_phone)
        if caller is None or target is None:
            raise TwilioHandoffError("caller and target must use E.164 format")
        if caller == target:
            raise TwilioHandoffError("refusing to transfer a call back to its caller")

        resolved_sid = (
            call_sid if self._valid_call_sid(call_sid) else self._find_active_call(caller)
        )
        twiml = (
            '<Response><Dial answerOnBridge="true" timeout="30" '
            f'callerId="{escape(self.credentials.caller_id)}">'
            f"<Number>{escape(target)}</Number></Dial></Response>"
        )
        response = self._client.post(
            self._call_url(resolved_sid),
            data={"Twiml": twiml},
        )
        self._raise_for_status(response, operation="redirect active call")
        return resolved_sid

    def _find_active_call(self, caller_phone: str) -> str:
        response = self._client.get(
            self._calls_url(),
            params={
                "Status": "in-progress",
                "From": caller_phone,
                "PageSize": 20,
            },
        )
        self._raise_for_status(response, operation="list active calls")
        payload = response.json()
        calls = payload.get("calls", []) if isinstance(payload, dict) else []
        candidates = [
            call
            for call in calls
            if isinstance(call, dict)
            and self._valid_call_sid(call.get("sid"))
            and str(call.get("status", "")).casefold() == "in-progress"
            and str(call.get("to", "")).casefold().startswith("sip:")
        ]
        if not candidates:
            raise TwilioHandoffError("no active SIP call matched the caller")
        candidates.sort(key=lambda call: str(call.get("date_created", "")), reverse=True)
        return str(candidates[0]["sid"])

    def _calls_url(self) -> str:
        return (
            f"https://api.twilio.com/2010-04-01/Accounts/{self.credentials.account_sid}/Calls.json"
        )

    def _call_url(self, call_sid: str) -> str:
        return (
            "https://api.twilio.com/2010-04-01/Accounts/"
            f"{self.credentials.account_sid}/Calls/{call_sid}.json"
        )

    @staticmethod
    def _valid_call_sid(value: Any) -> bool:
        return isinstance(value, str) and _CALL_SID.fullmatch(value) is not None

    @staticmethod
    def _raise_for_status(response: httpx.Response, *, operation: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise TwilioHandoffError(
                f"Twilio could not {operation}: HTTP {response.status_code}"
            ) from error
