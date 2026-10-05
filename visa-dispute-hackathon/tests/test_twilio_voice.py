import pytest

from dispute_agent.twilio_voice import (
    TwilioVoiceRequestError,
    build_openai_sip_twiml,
    is_twilio_voice_request,
    parse_voice_request,
)

ACCOUNT_SID = "AC" + "1" * 32
CALL_SID = "CA" + "2" * 32
PHONE = "+16615779964"
PROJECT = "proj_5tTah5HzJGr5gXEQbAZkBKYP"


def body(**overrides):
    values = {
        "AccountSid": ACCOUNT_SID,
        "CallSid": CALL_SID,
        "From": "+5511984348217",
        "To": PHONE,
    }
    values.update(overrides)
    return "&".join(f"{key}={value.replace('+', '%2B')}" for key, value in values.items()).encode()


def test_builds_programmable_voice_dial_to_openai_sip():
    request = parse_voice_request(body())

    twiml = build_openai_sip_twiml(
        request,
        expected_account_sid=ACCOUNT_SID,
        expected_called_phone=PHONE,
        openai_project_id=PROJECT,
    )

    assert '<Dial answerOnBridge="true" timeout="30">' in twiml
    assert f"sip:{PROJECT}@sip.api.openai.com;transport=tls" in twiml
    assert request.caller_phone == "+5511984348217"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"CallSid": "invalid"}, "CallSid"),
        ({"From": "123"}, "E.164"),
        ({"To": "123"}, "E.164"),
    ],
)
def test_rejects_malformed_voice_requests(overrides, expected):
    with pytest.raises(TwilioVoiceRequestError, match=expected):
        parse_voice_request(body(**overrides))


def test_rejects_wrong_account_or_called_number():
    request = parse_voice_request(body())
    with pytest.raises(TwilioVoiceRequestError, match="account"):
        build_openai_sip_twiml(
            request,
            expected_account_sid="AC" + "9" * 32,
            expected_called_phone=PHONE,
            openai_project_id=PROJECT,
        )
    with pytest.raises(TwilioVoiceRequestError, match="destination"):
        build_openai_sip_twiml(
            request,
            expected_account_sid=ACCOUNT_SID,
            expected_called_phone="+15551234567",
            openai_project_id=PROJECT,
        )


def test_matches_only_twilio_voice_route():
    assert is_twilio_voice_request({"rawPath": "/webhooks/twilio/voice"})
    assert is_twilio_voice_request({"path": "/webhooks/twilio/voice/"})
    assert not is_twilio_voice_request({"rawPath": "/webhooks/openai"})
