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
        "data": {
            "call_id": "call_1",
            "sip_headers": headers,
        },
    }


def tool_call_event(name: str, call_id: str, arguments: dict) -> str:
    return json.dumps(
        {
            "type": "response.done",
            "response": {
                "output": [
                    {
                        "type": "function_call",
                        "name": name,
                        "call_id": call_id,
                        "arguments": json.dumps(arguments),
                    }
                ]
            },
        }
    )


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
        self.controlled = []
        self.client = SimpleNamespace(realtime=SimpleNamespace(calls=FakeRealtimeCalls()))

    async def accept_call(
        self,
        call_id: str,
        caller_phone: str,
    ) -> None:
        self.accepted.append((call_id, caller_phone))

    async def control_call(
        self,
        call_id: str,
        caller_phone: str,
        *,
        max_duration_seconds: int | None = None,
    ) -> None:
        self.controlled.append(
            (
                call_id,
                caller_phone,
                max_duration_seconds,
            )
        )


class SipWebhookTests(unittest.TestCase):
    def test_extracts_e164_phone_from_sip_header(self):
        self.assertEqual(
            extract_caller_phone(incoming_event()),
            "+5511999990001",
        )

    def test_signed_incoming_event_is_scheduled_once(self):
        gateway = FakeGateway()
        verifier = SimpleNamespace(webhooks=FakeWebhooks(incoming_event()))
        client = TestClient(
            create_sip_app(
                FIXTURE,
                gateway=gateway,
                webhook_client=verifier,
            )
        )

        first = client.post(
            "/webhooks/openai",
            content=b"{}",
        )
        second = client.post(
            "/webhooks/openai",
            content=b"{}",
        )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(
            first.json(),
            {"status": "accepted"},
        )
        self.assertEqual(
            second.json(),
            {"status": "duplicate"},
        )
        self.assertEqual(
            gateway.accepted,
            [("call_1", "+5511999990001")],
        )

    def test_invalid_signature_is_rejected(self):
        gateway = FakeGateway()
        verifier = SimpleNamespace(webhooks=FakeWebhooks(error=ValueError("bad signature")))
        client = TestClient(
            create_sip_app(
                FIXTURE,
                gateway=gateway,
                webhook_client=verifier,
            )
        )

        response = client.post(
            "/webhooks/openai",
            content=b"{}",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(gateway.accepted, [])

    def test_missing_phone_rejects_sip_call(self):
        gateway = FakeGateway()
        verifier = SimpleNamespace(webhooks=FakeWebhooks(incoming_event(include_phone=False)))
        client = TestClient(
            create_sip_app(
                FIXTURE,
                gateway=gateway,
                webhook_client=verifier,
            )
        )

        response = client.post(
            "/webhooks/openai",
            content=b"{}",
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            gateway.client.realtime.calls.rejections,
            ["call_1"],
        )


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
        self.accepted.append(
            (
                call_id,
                configuration,
            )
        )


class RealtimeSidebandTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _gateway(events):
        websocket = FakeWebsocket(events)
        calls = FakeAcceptCalls()
        client = SimpleNamespace(realtime=SimpleNamespace(calls=calls))
        gateway = SipRealtimeGateway(
            FIXTURE,
            api_key="sk-test",
            openai_client=client,
            websocket_connect=FakeConnector(websocket),
        )
        return gateway, websocket, calls

    @staticmethod
    def _session_updates(websocket):
        return [event for event in websocket.sent if event.get("type") == "session.update"]

    @staticmethod
    def _tool_outputs(websocket):
        return [
            event for event in websocket.sent if event.get("type") == "conversation.item.create"
        ]

    async def test_customer_directory_is_loaded_only_for_a_valid_call(self):
        calls = FakeAcceptCalls()
        client = SimpleNamespace(realtime=SimpleNamespace(calls=calls))
        gateway = SipRealtimeGateway(
            FIXTURE,
            api_key="sk-test",
            openai_client=client,
        )

        self.assertIsNone(gateway._calls)

        state = gateway.calls.start(
            "+5511999990001",
            call_id="call_lazy",
        )

        self.assertIsNotNone(gateway._calls)
        self.assertEqual(
            state.stage,
            "needs_language_confirmation",
        )

    async def test_confirm_language_then_phone_authentication_succeeds(self):
        events = [
            tool_call_event(
                "confirm_language",
                "tool_language",
                {},
            ),
            tool_call_event(
                "set_authentication_method",
                "tool_auth",
                {"method": "phone"},
            ),
        ]

        gateway, websocket, calls = self._gateway(events)

        await gateway.accept_and_control(
            "call_phone",
            "+5511999990001",
        )

        state = gateway.calls.get("call_phone")

        self.assertEqual(
            state.stage,
            "authenticated",
        )
        self.assertEqual(
            state.identity.customer_id,
            "CLI-002",
        )
        self.assertEqual(
            state.authentication_method,
            "phone",
        )
        self.assertEqual(
            calls.accepted[0][0],
            "call_phone",
        )

        session_updates = self._session_updates(websocket)
        tool_outputs = self._tool_outputs(websocket)

        # Initial server instructions + language confirmation + auth method.
        self.assertEqual(
            len(session_updates),
            3,
        )
        self.assertEqual(
            len(tool_outputs),
            2,
        )

        for update in session_updates:
            self.assertEqual(
                update["session"]["type"],
                "realtime",
            )

        self.assertIn(
            "pt-BR",
            session_updates[0]["session"]["instructions"],
        )
        self.assertIn(
            "needs_auth_method",
            session_updates[1]["session"]["instructions"],
        )
        self.assertIn(
            "authenticated",
            session_updates[-1]["session"]["instructions"],
        )

        outbound = json.dumps(
            websocket.sent,
            ensure_ascii=False,
        )
        self.assertIn("Izzy", outbound)
        self.assertIn("Factored Bank", outbound)

    async def test_phone_failure_falls_back_to_document_and_dtmf_authenticates(self):
        events = [
            tool_call_event(
                "confirm_language",
                "tool_language",
                {},
            ),
            tool_call_event(
                "set_authentication_method",
                "tool_auth",
                {"method": "phone"},
            ),
        ] + [
            json.dumps(
                {
                    "type": "transport.dtmf.received",
                    "event": key,
                }
            )
            for key in "123456789#"
        ]

        gateway, websocket, _ = self._gateway(events)

        await gateway.accept_and_control(
            "call_fallback",
            "+573009998877",
        )

        state = gateway.calls.get("call_fallback")

        self.assertEqual(
            state.stage,
            "authenticated",
        )
        self.assertEqual(
            state.identity.customer_id,
            "CLI-001",
        )
        self.assertEqual(
            state.authentication_method,
            "document",
        )

        session_updates = self._session_updates(websocket)

        self.assertEqual(
            len(session_updates),
            3,
        )
        self.assertIn(
            "es-CO",
            session_updates[0]["session"]["instructions"],
        )
        self.assertIn(
            "needs_document",
            session_updates[-1]["session"]["instructions"],
        )

        outbound = json.dumps(
            websocket.sent,
            ensure_ascii=False,
        )

        # The model may be told that document authentication is required, but
        # the document digits themselves must never be sent back to Realtime.
        self.assertNotIn(
            "123456789",
            outbound,
        )

    async def test_language_change_then_direct_document_authentication(self):
        events = [
            tool_call_event(
                "set_language",
                "tool_language",
                {
                    "language": "es",
                    "accent": "colombian",
                },
            ),
            tool_call_event(
                "set_authentication_method",
                "tool_auth",
                {"method": "document"},
            ),
        ] + [
            json.dumps(
                {
                    "type": "transport.dtmf.received",
                    "event": key,
                }
            )
            for key in "123456789#"
        ]

        gateway, websocket, _ = self._gateway(events)

        await gateway.accept_and_control(
            "call_document",
            "+5511888887777",
        )

        state = gateway.calls.get("call_document")

        self.assertEqual(
            state.stage,
            "authenticated",
        )
        self.assertEqual(
            state.identity.customer_id,
            "CLI-001",
        )
        self.assertEqual(
            state.authentication_method,
            "document",
        )
        self.assertEqual(
            state.locale.locale,
            "es-CO",
        )

        session_updates = self._session_updates(websocket)
        tool_outputs = self._tool_outputs(websocket)

        self.assertEqual(
            len(session_updates),
            3,
        )
        self.assertEqual(
            len(tool_outputs),
            2,
        )

        self.assertIn(
            "pt-BR",
            session_updates[0]["session"]["instructions"],
        )
        self.assertIn(
            "es-CO",
            session_updates[1]["session"]["instructions"],
        )
        self.assertIn(
            "needs_document",
            session_updates[-1]["session"]["instructions"],
        )

        outbound = json.dumps(
            websocket.sent,
            ensure_ascii=False,
        )
        self.assertNotIn(
            "123456789",
            outbound,
        )


if __name__ == "__main__":
    unittest.main()
