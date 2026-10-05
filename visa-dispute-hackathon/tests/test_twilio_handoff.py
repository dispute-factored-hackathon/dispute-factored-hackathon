import httpx
import pytest

from dispute_agent.twilio_handoff import (
    TwilioCallHandoff,
    TwilioHandoffCredentials,
    TwilioHandoffError,
)

ACCOUNT_SID = "AC" + "1" * 32
API_KEY_SID = "SK" + "2" * 32
CALL_SID = "CA" + "3" * 32
PARENT_CALL_SID = "CA" + "4" * 32


def credentials():
    return TwilioHandoffCredentials(
        account_sid=ACCOUNT_SID,
        api_key_sid=API_KEY_SID,
        api_key_secret="secret",
        caller_id="+16615779964",
    )


def test_redirects_known_call_with_twilio_owned_caller_id():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"parent_call_sid": PARENT_CALL_SID})
        return httpx.Response(200, json={"sid": CALL_SID})

    handoff = TwilioCallHandoff(credentials(), transport=httpx.MockTransport(handler))
    result = handoff.transfer(
        caller_phone="+5511984348217",
        target_phone="+5511981020050",
        call_sid=CALL_SID,
    )

    assert result == PARENT_CALL_SID
    assert [request.method for request in requests] == ["GET", "POST"]
    assert PARENT_CALL_SID in str(requests[1].url)
    body = requests[1].content.decode()
    assert "%2B16615779964" in body
    assert "%2B5511981020050" in body


def test_finds_current_sip_call_when_header_has_no_call_sid():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            if CALL_SID in str(request.url):
                return httpx.Response(200, json={"parent_call_sid": PARENT_CALL_SID})
            return httpx.Response(
                200,
                json={
                    "calls": [
                        {
                            "sid": CALL_SID,
                            "status": "in-progress",
                            "to": "sip:project@sip.api.openai.com",
                            "date_created": "Sun, 05 Oct 2026 17:09:00 +0000",
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"sid": CALL_SID})

    handoff = TwilioCallHandoff(credentials(), transport=httpx.MockTransport(handler))
    result = handoff.transfer(
        caller_phone="+5511984348217",
        target_phone="+5511981020050",
    )

    assert result == PARENT_CALL_SID
    assert [request.method for request in requests] == ["GET", "GET", "POST"]
    assert "From=%2B5511984348217" in str(requests[0].url)


def test_fails_closed_when_sip_leg_has_no_programmable_voice_parent():
    handoff = TwilioCallHandoff(
        credentials(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"parent_call_sid": None})
        ),
    )

    with pytest.raises(TwilioHandoffError, match="no Programmable Voice parent"):
        handoff.transfer(
            caller_phone="+5511984348217",
            target_phone="+5511981020050",
            call_sid=CALL_SID,
        )


def test_fails_closed_when_no_active_sip_call_matches():
    handoff = TwilioCallHandoff(
        credentials(),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"calls": []})),
    )

    with pytest.raises(TwilioHandoffError, match="no active SIP call"):
        handoff.transfer(
            caller_phone="+5511984348217",
            target_phone="+5511981020050",
        )
