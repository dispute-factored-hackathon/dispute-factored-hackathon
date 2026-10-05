"""Twilio Programmable Voice ingress for the OpenAI Realtime SIP leg."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from html import escape
from urllib.parse import parse_qs

from .human_handoff import normalize_e164

_CALL_SID = re.compile(r"^CA[0-9a-fA-F]{32}$")
_PROJECT_ID = re.compile(r"^proj_[A-Za-z0-9]+$")


class TwilioVoiceRequestError(ValueError):
    """Raised when an incoming Voice webhook is incomplete or unexpected."""


@dataclass(frozen=True)
class TwilioVoiceRequest:
    call_sid: str
    account_sid: str
    caller_phone: str
    called_phone: str


def parse_voice_request(body: bytes) -> TwilioVoiceRequest:
    """Parse the fields required to safely route an incoming Twilio call."""

    values = parse_qs(body.decode("utf-8"), keep_blank_values=True)

    def required(name: str) -> str:
        value = values.get(name, [""])[0].strip()
        if not value:
            raise TwilioVoiceRequestError(f"missing Twilio field: {name}")
        return value

    call_sid = required("CallSid")
    account_sid = required("AccountSid")
    caller_phone = normalize_e164(required("From"))
    called_phone = normalize_e164(required("To"))
    if _CALL_SID.fullmatch(call_sid) is None:
        raise TwilioVoiceRequestError("invalid Twilio CallSid")
    if not account_sid.startswith("AC"):
        raise TwilioVoiceRequestError("invalid Twilio AccountSid")
    if caller_phone is None or called_phone is None:
        raise TwilioVoiceRequestError("Twilio phone numbers must use E.164 format")
    return TwilioVoiceRequest(call_sid, account_sid, caller_phone, called_phone)


def build_openai_sip_twiml(
    request: TwilioVoiceRequest,
    *,
    expected_account_sid: str,
    expected_called_phone: str,
    openai_project_id: str,
) -> str:
    """Return TwiML only for calls belonging to this account and number."""

    if request.account_sid != expected_account_sid:
        raise TwilioVoiceRequestError("unexpected Twilio account")
    if request.called_phone != normalize_e164(expected_called_phone):
        raise TwilioVoiceRequestError("unexpected destination number")
    if _PROJECT_ID.fullmatch(openai_project_id) is None:
        raise TwilioVoiceRequestError("invalid OpenAI project ID")

    sip_uri = f"sip:{openai_project_id}@sip.api.openai.com;transport=tls"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response><Dial answerOnBridge="true" timeout="30">'
        f"<Sip>{escape(sip_uri)}</Sip>"
        "</Dial></Response>"
    )


def is_twilio_voice_request(event: Mapping[str, object]) -> bool:
    """Recognize the dedicated Function URL route without affecting workers."""

    path = str(event.get("rawPath") or event.get("path") or "")
    return path.rstrip("/") == "/webhooks/twilio/voice"
