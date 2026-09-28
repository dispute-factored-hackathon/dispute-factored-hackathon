import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from dispute_agent.sip_realtime import (
    SipRealtimeGateway,
    create_sip_app,
    extract_caller_phone,
)

FIXTURE = Path(__file__).parent / "fixtures" / "customers.csv"


def incoming_event(*, event_id="evt_1", include_phone=True):
    headers = (
        [{"name": "From", "value": "<sip:+5511999990001@sip.example.com>"}] if include_phone else []
    )
    return {
        "id": event_id,
        "type": "realtime.call.incoming",
        "data": {"call_id": "call_1", "sip_headers": headers},
    }


class FakeWebhooks:
    def __init__(self, event=None, error=None):
        self.event = event
        self.error = error

    def unwrap(self, body, headers):
        if self.error:
            raise self.error
        return self.event


class FakeRealtimeCalls:
    def __init__(self):
        self.rejections = []

    def reject(self, call_id):
        self.rejections.append(call_id)


class FakeGateway:
    def __init__(self):
        self.accepted = []
        self.client = SimpleNamespace(realtime=SimpleNamespace(calls=FakeRealtimeCalls()))

    async def accept_and_control(self, call_id, caller_phone):
        self.accepted.append((call_id, caller_phone))


class SipWebhookTests(unittest.TestCase):
    def test_extracts_e164_phone_from_sip_header(self):
        self.assertEqual(extract_caller_phone(incoming_event()), "+5511999990001")

    def test_signed_incoming_event_is_scheduled_once(self):
        gateway = FakeGateway()
        verifier = SimpleNamespace(webhooks=FakeWebhooks(incoming_event()))
        client = TestClient(create_sip_app(FIXTURE, gateway=gateway, webhook_client=verifier))

        first = client.post("/webhooks/openai", content=b"{}")
        second = client.post("/webhooks/openai", content=b"{}")

        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.json(), {"status": "accepted"})
        self.assertEqual(second.json(), {"status": "duplicate"})
        self.assertEqual(gateway.accepted, [("call_1", "+5511999990001")])

    def test_invalid_signature_is_rejected(self):
        gateway = FakeGateway()
        verifier = SimpleNamespace(webhooks=FakeWebhooks(error=ValueError("bad signature")))
        client = TestClient(create_sip_app(FIXTURE, gateway=gateway, webhook_client=verifier))

        response = client.post("/webhooks/openai", content=b"{}")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(gateway.accepted, [])

    def test_missing_phone_rejects_sip_call(self):
        gateway = FakeGateway()
        verifier = SimpleNamespace(webhooks=FakeWebhooks(incoming_event(include_phone=False)))
        client = TestClient(create_sip_app(FIXTURE, gateway=gateway, webhook_client=verifier))

        response = client.post("/webhooks/openai", content=b"{}")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(gateway.client.realtime.calls.rejections, ["call_1"])


class FakeWebsocket:
    def __init__(self, events):
        self.events = iter(events)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.events)
        except StopIteration as error:
            raise StopAsyncIteration from error

    async def send(self, message):
        self.sent.append(json.loads(message))


class FakeConnector:
    def __init__(self, websocket):
        self.websocket = websocket

    def __call__(self, url, **kwargs):
        return self.websocket


class FakeAcceptCalls:
    def __init__(self):
        self.accepted = []

    def accept(self, call_id, **configuration):
        self.accepted.append((call_id, configuration))


class RealtimeSidebandTests(unittest.IsolatedAsyncioTestCase):
    async def test_customer_directory_is_loaded_only_for_a_valid_call(self):
        calls = FakeAcceptCalls()
        client = SimpleNamespace(realtime=SimpleNamespace(calls=calls))
        gateway = SipRealtimeGateway(FIXTURE, api_key="sk-test", openai_client=client)

        self.assertIsNone(gateway._calls)
        gateway.calls.start("+5511999990001")
        self.assertIsNotNone(gateway._calls)

    async def test_language_tool_then_dtmf_authentication(self):
        language_call = {
            "type": "response.done",
            "response": {
                "output": [
                    {
                        "type": "function_call",
                        "name": "set_language",
                        "call_id": "tool_1",
                        "arguments": '{"language":"es","accent":"colombian"}',
                    }
                ]
            },
        }
        events = [json.dumps(language_call)] + [
            json.dumps({"type": "transport.dtmf.received", "event": key}) for key in "123456789#"
        ]
        websocket = FakeWebsocket(events)
        calls = FakeAcceptCalls()
        client = SimpleNamespace(realtime=SimpleNamespace(calls=calls))
        gateway = SipRealtimeGateway(
            FIXTURE,
            api_key="sk-test",
            openai_client=client,
            websocket_connect=FakeConnector(websocket),
        )

        await gateway.accept_and_control("call_unknown", "+573009998877")

        state = gateway.calls.get("call_unknown")
        self.assertEqual(state.stage, "authenticated")
        self.assertEqual(state.identity.customer_id, "CLI-001")
        self.assertEqual(calls.accepted[0][0], "call_unknown")
        tool_outputs = [
            event for event in websocket.sent if event.get("type") == "conversation.item.create"
        ]
        session_updates = [
            event for event in websocket.sent if event.get("type") == "session.update"
        ]
        self.assertEqual(len(tool_outputs), 1)
        self.assertEqual(len(session_updates), 1)
        self.assertIn("es-CO", session_updates[0]["session"]["instructions"])
        self.assertNotIn("123456789", json.dumps(websocket.sent))


if __name__ == "__main__":
    unittest.main()
