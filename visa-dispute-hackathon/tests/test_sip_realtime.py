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
from dispute_agent.transaction_search import (
    SQLiteTransactionSearchRepository,
    TransactionSearchCriteria,
)
from dispute_agent.voice_call import TransactionSelectionOutcome
from webapp.backend.repositories.mock import MockComplaintRepository

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


def session_updated_event() -> str:
    return json.dumps(
        {
            "type": "session.updated",
            "session": {
                "type": "realtime",
            },
        }
    )


def dtmf_event(key: str) -> str:
    return json.dumps(
        {
            "type": "input_audio_buffer.dtmf_event_received",
            "event": key,
        }
    )


def completed_transcript_event(*, speaker: str, transcript: str) -> str:
    if speaker == "customer":
        return json.dumps(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "item_customer_1",
                "transcript": transcript,
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "type": "response.output_audio_transcript.done",
            "item_id": "item_agent_1",
            "response_id": "response_1",
            "transcript": transcript,
        },
        ensure_ascii=False,
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
    def __init__(self, *, refer_error=None):
        self.accepted = []
        self.referrals = []
        self.refer_error = refer_error

    def accept(self, call_id, **configuration):
        self.accepted.append(
            (
                call_id,
                configuration,
            )
        )

    def refer(self, call_id, *, target_uri):
        if self.refer_error is not None:
            raise self.refer_error
        self.referrals.append((call_id, target_uri))


class FailingComplaintRepository(MockComplaintRepository):
    def create(self, complaint):
        del complaint
        raise RuntimeError("synthetic complaint storage failure")


class RealtimeSidebandTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _gateway(
        events,
        *,
        transaction_repository=None,
        complaint_repository=None,
        human_handoff_number=None,
        refer_error=None,
    ):
        websocket = FakeWebsocket(events)
        calls = FakeAcceptCalls(refer_error=refer_error)
        client = SimpleNamespace(realtime=SimpleNamespace(calls=calls))
        gateway = SipRealtimeGateway(
            FIXTURE,
            api_key="sk-test",
            openai_client=client,
            websocket_connect=FakeConnector(websocket),
            transaction_repository=transaction_repository,
            complaint_repository=complaint_repository,
            human_handoff_number=human_handoff_number,
        )
        return gateway, websocket, calls

    async def test_explicit_human_request_transfers_after_spoken_notice(self):
        events = [
            session_updated_event(),
            completed_transcript_event(
                speaker="customer",
                transcript="Quero falar com uma pessoa.",
            ),
            tool_call_event("request_human", "tool_human", {}),
            json.dumps({"type": "response.done", "response": {"output": []}}),
        ]
        gateway, websocket, calls = self._gateway(
            events,
            human_handoff_number="+5511981020050",
        )

        await gateway.accept_and_control("call_human", "+5511999990001")

        self.assertEqual(calls.referrals, [("call_human", "tel:+5511981020050")])
        self.assertEqual(gateway.calls.get("call_human").stage, "handoff")
        spoken = [
            event["response"]["instructions"]
            for event in websocket.sent
            if event.get("type") == "response.create"
        ]
        self.assertTrue(any("transferir você agora" in message for message in spoken))

    async def test_handoff_waits_when_tool_call_arrives_before_transcript(self):
        events = [
            session_updated_event(),
            tool_call_event("request_human", "tool_human", {}),
            completed_transcript_event(
                speaker="customer",
                transcript="Eu quero falar com um ser humano.",
            ),
            json.dumps({"type": "response.done", "response": {"output": []}}),
        ]
        gateway, websocket, calls = self._gateway(
            events,
            human_handoff_number="+5511981020050",
        )

        await gateway.accept_and_control("call_late_transcript", "+5511999990001")

        self.assertEqual(
            calls.referrals,
            [("call_late_transcript", "tel:+5511981020050")],
        )
        tool_output = self._tool_outputs(websocket)[-1]["item"]["output"]
        self.assertIn("transferir você agora", tool_output)

    async def test_failed_late_transcription_asks_to_repeat_human_request(self):
        events = [
            session_updated_event(),
            tool_call_event("request_human", "tool_human", {}),
            json.dumps(
                {
                    "type": "conversation.item.input_audio_transcription.failed",
                    "item_id": "item_customer_1",
                }
            ),
        ]
        gateway, websocket, calls = self._gateway(
            events,
            human_handoff_number="+5511981020050",
        )

        await gateway.accept_and_control("call_failed_transcript", "+5511999990001")

        self.assertEqual(calls.referrals, [])
        self.assertEqual(
            gateway.calls.get("call_failed_transcript").stage,
            "needs_language_confirmation",
        )
        tool_output = self._tool_outputs(websocket)[-1]["item"]["output"]
        self.assertIn("Não consegui confirmar", tool_output)

    async def test_handoff_does_not_transfer_back_to_calling_phone(self):
        events = [
            session_updated_event(),
            tool_call_event("request_human", "tool_human", {}),
            completed_transcript_event(
                speaker="customer",
                transcript="Quero um atendente humano.",
            ),
        ]
        gateway, websocket, calls = self._gateway(
            events,
            human_handoff_number="+5511981020050",
        )

        await gateway.accept_and_control("call_self", "+5511981020050")

        self.assertEqual(calls.referrals, [])
        tool_output = self._tool_outputs(websocket)[-1]["item"]["output"]
        self.assertIn("mesmo número", tool_output)

    async def test_handoff_failure_preserves_progress_and_explains_failure(self):
        events = [
            session_updated_event(),
            completed_transcript_event(
                speaker="customer",
                transcript="Preciso falar com uma pessoa.",
            ),
            tool_call_event("request_human", "tool_human", {}),
            json.dumps({"type": "response.done", "response": {"output": []}}),
            json.dumps({"type": "response.done", "response": {"output": []}}),
        ]
        gateway, websocket, calls = self._gateway(
            events,
            human_handoff_number="+5511981020050",
            refer_error=RuntimeError("synthetic transfer failure"),
        )

        await gateway.accept_and_control("call_failed_handoff", "+5511999990001")

        self.assertEqual(calls.referrals, [])
        self.assertEqual(gateway.calls.get("call_failed_handoff").stage, "handoff")
        spoken = [
            event["response"]["instructions"]
            for event in websocket.sent
            if event.get("type") == "response.create"
        ]
        self.assertTrue(any("Não consegui completar a transferência" in item for item in spoken))

    async def test_exhausted_document_authentication_uses_same_real_handoff(self):
        events = [
            session_updated_event(),
            tool_call_event("confirm_language", "tool_language", {}),
            tool_call_event(
                "set_authentication_method",
                "tool_auth",
                {"method": "document"},
            ),
            *[dtmf_event(key) for key in "000#000#000#"],
            json.dumps({"type": "response.done", "response": {"output": []}}),
        ]
        gateway, _, calls = self._gateway(
            events,
            human_handoff_number="+5511981020050",
        )

        await gateway.accept_and_control("call_auth_exhausted", "+5511999990001")

        self.assertEqual(
            calls.referrals,
            [("call_auth_exhausted", "tel:+5511981020050")],
        )
        state = gateway.calls.get("call_auth_exhausted")
        self.assertEqual(state.handoff_reason, "authentication_attempts_exhausted")

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

    async def test_uses_cedar_as_default_voice(self):
        gateway, _, calls = self._gateway([])

        await gateway.accept_call(
            "call_voice",
            "+5511999990001",
        )

        _, configuration = calls.accepted[0]
        self.assertEqual(gateway.voice, "cedar")
        self.assertEqual(configuration["audio"]["output"]["voice"], "cedar")

    async def test_enables_input_transcription_in_accept_and_session_update(self):
        gateway, websocket, calls = self._gateway([session_updated_event()])

        await gateway.accept_and_control(
            "call_transcription_configuration",
            "+5511999990001",
        )

        _, configuration = calls.accepted[0]
        expected = {"model": "gpt-4o-mini-transcribe"}
        self.assertEqual(configuration["audio"]["input"]["transcription"], expected)
        self.assertEqual(
            self._session_updates(websocket)[0]["session"]["audio"]["input"]["transcription"],
            expected,
        )

    async def test_logs_complete_customer_and_agent_transcripts_without_redaction(self):
        customer_transcript = "Meu nome mock é João; falei R$ 13,47 & nada deve sumir."
        agent_transcript = "Entendi João — encontrei a compra mock de R$ 13,47."
        gateway, _, _ = self._gateway(
            [
                session_updated_event(),
                completed_transcript_event(
                    speaker="customer",
                    transcript=customer_transcript,
                ),
                completed_transcript_event(
                    speaker="agent",
                    transcript=agent_transcript,
                ),
            ]
        )

        with self.assertLogs("dispute_agent.sip_realtime", level="INFO") as captured:
            await gateway.accept_and_control(
                "call_full_transcript",
                "+5511999990001",
            )

        transcript_events = [
            json.loads(line.split("INFO:dispute_agent.sip_realtime:", 1)[-1])
            for line in captured.output
            if '"event": "voice.transcript.completed"' in line
        ]
        self.assertEqual(
            [(event["speaker"], event["transcript"]) for event in transcript_events],
            [
                ("customer", customer_transcript),
                ("agent", agent_transcript),
            ],
        )
        self.assertTrue(all(event["redacted"] is False for event in transcript_events))

    async def test_can_disable_full_transcript_logs_outside_demo(self):
        websocket = FakeWebsocket(
            [
                session_updated_event(),
                completed_transcript_event(
                    speaker="customer",
                    transcript="do not persist this",
                ),
            ]
        )
        calls = FakeAcceptCalls()
        gateway = SipRealtimeGateway(
            FIXTURE,
            api_key="sk-test",
            openai_client=SimpleNamespace(realtime=SimpleNamespace(calls=calls)),
            websocket_connect=FakeConnector(websocket),
            log_full_transcripts=False,
        )

        with self.assertLogs("dispute_agent.sip_realtime", level="INFO") as captured:
            await gateway.accept_and_control(
                "call_transcript_disabled",
                "+5511999990001",
            )

        self.assertIsNone(calls.accepted[0][1]["audio"]["input"]["transcription"])
        self.assertNotIn("do not persist this", "\n".join(captured.output))

    async def test_opening_waits_for_session_updated(self):
        events = [
            json.dumps(
                {
                    "type": "response.created",
                    "response": {
                        "id": "resp_existing",
                    },
                }
            ),
            json.dumps(
                {
                    "type": "response.done",
                    "response": {
                        "id": "resp_existing",
                        "output": [],
                    },
                }
            ),
            session_updated_event(),
        ]

        gateway, websocket, _ = self._gateway(events)

        await gateway.accept_and_control(
            "call_startup",
            "+5511999990001",
        )

        sent_types = [event.get("type") for event in websocket.sent]

        self.assertGreaterEqual(
            sent_types.count("session.update"),
            1,
        )
        self.assertEqual(
            sent_types.count("response.create"),
            1,
        )

        initial_session_index = sent_types.index("session.update")
        opening_index = sent_types.index("response.create")

        self.assertLess(
            initial_session_index,
            opening_index,
        )

        opening = next(event for event in websocket.sent if event.get("type") == "response.create")
        instructions = opening["response"]["instructions"]

        self.assertIn("Izzy", instructions)
        self.assertIn("Factored Bank", instructions)
        self.assertEqual(opening["response"]["tool_choice"], "none")

    async def test_confirm_language_then_phone_authentication_succeeds(self):
        events = [
            session_updated_event(),
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

    async def test_unclear_language_does_not_change_language_or_advance(self):
        events = [
            session_updated_event(),
            tool_call_event(
                "set_language",
                "tool_language_unclear",
                {"language": "unclear"},
            ),
        ]
        gateway, websocket, _ = self._gateway(events)

        await gateway.accept_and_control("call_unclear_language", "+5511999990001")

        state = gateway.calls.get("call_unclear_language")
        self.assertEqual(state.stage, "needs_language_confirmation")
        self.assertEqual(state.locale.language, "pt")
        outbound = json.dumps(websocket.sent, ensure_ascii=False)
        self.assertIn(
            "Não consegui identificar o idioma na sua resposta.",
            outbound,
        )

    async def test_short_noisy_transcript_cannot_switch_language(self):
        events = [
            session_updated_event(),
            completed_transcript_event(speaker="customer", transcript="H"),
            tool_call_event(
                "set_language",
                "tool_language_noise",
                {"language": "en", "accent": "american"},
            ),
        ]
        gateway, websocket, _ = self._gateway(events)

        await gateway.accept_and_control("call_language_noise", "+5511999990001")

        state = gateway.calls.get("call_language_noise")
        self.assertEqual(state.stage, "needs_language_confirmation")
        self.assertEqual(state.locale.locale, "pt-BR")
        self.assertIn("continuar neste idioma", json.dumps(websocket.sent, ensure_ascii=False))

    async def test_unrelated_multiword_transcript_cannot_keep_language(self):
        events = [
            session_updated_event(),
            completed_transcript_event(speaker="customer", transcript="banana apple"),
            tool_call_event(
                "set_language",
                "tool_language_unrelated",
                {"language": "keep"},
            ),
        ]
        gateway, websocket, _ = self._gateway(events)

        await gateway.accept_and_control("call_language_unrelated", "+5511999990001")

        state = gateway.calls.get("call_language_unrelated")
        self.assertEqual(state.stage, "needs_language_confirmation")
        self.assertIn("continuar neste idioma", json.dumps(websocket.sent, ensure_ascii=False))

    async def test_unclear_authentication_method_does_not_authenticate(self):
        events = [
            session_updated_event(),
            tool_call_event("confirm_language", "tool_language", {}),
            tool_call_event(
                "set_authentication_method",
                "tool_auth_unclear",
                {"method": "unclear"},
            ),
        ]
        gateway, websocket, _ = self._gateway(events)

        await gateway.accept_and_control("call_unclear_auth", "+5511999990001")

        state = gateway.calls.get("call_unclear_auth")
        self.assertEqual(state.stage, "needs_auth_method")
        self.assertIsNone(state.identity)
        outbound = json.dumps(websocket.sent, ensure_ascii=False)
        self.assertIn(
            "escolha autenticação pelo número de telefone desta ligação ou pelo documento",
            outbound,
        )

    async def test_language_change_after_authentication_keeps_authenticated_session(self):
        events = [
            session_updated_event(),
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
            tool_call_event(
                "set_language",
                "tool_change_language",
                {"language": "en", "accent": "american"},
            ),
        ]

        gateway, websocket, _ = self._gateway(events)

        await gateway.accept_and_control(
            "call_authenticated_language_change",
            "+5511999990001",
        )

        state = gateway.calls.get("call_authenticated_language_change")
        self.assertEqual(state.stage, "authenticated")
        self.assertEqual(state.identity.customer_id, "CLI-002")
        self.assertEqual(state.locale.locale, "en-US")

        outbound = json.dumps(websocket.sent, ensure_ascii=False)
        self.assertIn(
            "Language changed to US English. We can continue your card dispute.",
            outbound,
        )
        self.assertNotIn(
            "would you prefer to authenticate using the phone number",
            outbound,
        )

    async def test_portuguese_choice_from_brazil_preserves_brazilian_locale(self):
        events = [
            session_updated_event(),
            tool_call_event("confirm_language", "tool_language", {}),
            tool_call_event(
                "set_authentication_method",
                "tool_auth",
                {"method": "phone"},
            ),
            completed_transcript_event(
                speaker="customer",
                transcript="Quero falar em português brasileiro.",
            ),
            tool_call_event(
                "set_language",
                "tool_change_language",
                {"language": "pt", "accent": "portuguese"},
            ),
        ]
        gateway, websocket, _ = self._gateway(events)

        await gateway.accept_and_control("call_brazilian_portuguese", "+5511999990001")

        state = gateway.calls.get("call_brazilian_portuguese")
        self.assertEqual(state.locale.locale, "pt-BR")
        self.assertEqual(state.locale.accent, "brazilian")
        self.assertIn(
            "Idioma alterado para português brasileiro",
            json.dumps(websocket.sent, ensure_ascii=False),
        )
        instructions = self._session_updates(websocket)[-1]["session"]["instructions"]
        self.assertIn("Speak in pt-BR", instructions)

    async def test_phone_failure_falls_back_to_document_and_dtmf_authenticates(self):
        events = [
            session_updated_event(),
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
        ] + [dtmf_event(key) for key in "123456789#"]

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

        # OpenAI SIP emits input_audio_buffer.dtmf_event_received. The model may
        # be told that document authentication is required, but the document
        # digits themselves must never be sent back to Realtime.
        self.assertNotIn(
            "123456789",
            outbound,
        )

    async def test_language_change_then_direct_document_authentication(self):
        events = [
            session_updated_event(),
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
        ] + [dtmf_event(key) for key in "123456789#"]

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

    async def test_authenticated_caller_searches_and_confirms_transaction(self):
        events = [
            session_updated_event(),
            tool_call_event("confirm_language", "tool_language", {}),
            tool_call_event(
                "set_authentication_method",
                "tool_auth",
                {"method": "phone"},
            ),
            tool_call_event(
                "search_transactions",
                "tool_search",
                {"approximate_amount": 13, "currency": "USD"},
            ),
            completed_transcript_event(
                speaker="customer",
                transcript="Sim.",
            ),
            tool_call_event(
                "confirm_transaction",
                "tool_confirm_transaction",
                {"confirmation_intent": "CONFIRM"},
            ),
            tool_call_event(
                "classify_dispute",
                "tool_classify_dispute",
                {
                    "allegation": "UNAUTHORIZED_CARD",
                    "customer_denies_authorization": True,
                    "customer_reports_duplicate": False,
                },
            ),
            completed_transcript_event(speaker="customer", transcript="Quatro."),
            tool_call_event(
                "record_csat",
                "tool_csat",
                {"response_intent": "RATING", "rating": 4},
            ),
        ]
        transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.addCleanup(transactions.close)
        gateway, websocket, calls = self._gateway(
            events,
            transaction_repository=transactions,
        )

        await gateway.accept_and_control(
            "call_transaction_search",
            "+5511999990001",
        )

        state = gateway.calls.get("call_transaction_search")
        self.assertEqual(state.stage, "completed")
        self.assertEqual(state.confirmed_transaction.merchant_name, "Lemon Drop Market")
        self.assertEqual(state.dispute_classification.visa_condition_code, "10.4")
        self.assertIsNotNone(state.complaint_id)
        self.assertEqual(state.complaint_status, "In Review")

        configured_tools = {tool["name"] for tool in calls.accepted[0][1]["tools"]}
        self.assertIn("search_transactions", configured_tools)
        self.assertIn("confirm_transaction", configured_tools)
        self.assertIn("classify_dispute", configured_tools)
        self.assertIn("record_csat", configured_tools)

        interaction_id = gateway.calls.call_interactions.interaction_id(state.call_id)
        survey = gateway.calls.call_interactions.surveys.get_by_interaction(interaction_id)
        agent = gateway.calls.call_interactions.agents.get_by_id("AGENT-IZZY")
        transcript = gateway.calls.call_interactions.transcripts.get_by_interaction(interaction_id)
        self.assertEqual(survey.main_score, 4)
        self.assertEqual(agent.avg_csat, 4.0)
        self.assertIn("Quatro.", transcript.customer_text)

        outbound = json.dumps(websocket.sent, ensure_ascii=False)
        self.assertIn("Lemon Drop Market", outbound)
        self.assertIn("12,49", outbound)
        self.assertIn("não fez nem autorizou", outbound)
        self.assertIn("código Visa candidato é 10.4", outbound)
        self.assertIn("cartão final 9999 foi bloqueado", outbound)
        self.assertIn(f"A reclamação {state.complaint_id} foi aberta", outbound)
        self.assertIn("com esse código Visa", outbound)
        self.assertIn("status Em análise", outbound)
        self.assertIn("como você avalia este atendimento de 1 a 5", outbound)
        self.assertIn("Obrigado pela avaliação", outbound)
        self.assertNotIn("9999999999999999", outbound)
        self.assertNotIn("SELECT", outbound)
        self.assertNotIn(state.confirmed_transaction.transaction_id, outbound)
        response_creates = [
            event for event in websocket.sent if event.get("type") == "response.create"
        ]
        self.assertTrue(any("instructions" in event["response"] for event in response_creates))

    async def test_duplicate_report_maps_to_visa_12_6_1(self):
        events = [
            session_updated_event(),
            tool_call_event("confirm_language", "tool_language", {}),
            tool_call_event(
                "set_authentication_method",
                "tool_auth",
                {"method": "phone"},
            ),
            tool_call_event(
                "search_transactions",
                "tool_search",
                {"merchant_query": "lemon"},
            ),
            completed_transcript_event(speaker="customer", transcript="Sim."),
            tool_call_event(
                "confirm_transaction",
                "tool_confirm",
                {"confirmation_intent": "CONFIRM"},
            ),
            tool_call_event(
                "classify_dispute",
                "tool_classify",
                {
                    "allegation": "DUPLICATE_PROCESSING",
                    "customer_denies_authorization": False,
                    "customer_reports_duplicate": True,
                },
            ),
        ]
        transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.addCleanup(transactions.close)
        gateway, websocket, _ = self._gateway(events, transaction_repository=transactions)

        await gateway.accept_and_control("call_duplicate_classification", "+5511999990001")

        state = gateway.calls.get("call_duplicate_classification")
        self.assertEqual(state.stage, "dispute_classified")
        self.assertEqual(state.dispute_classification.visa_condition_code, "12.6.1")
        self.assertIsNotNone(state.complaint_id)
        outbound = json.dumps(websocket.sent, ensure_ascii=False)
        self.assertIn("processamento duplicado", outbound)
        self.assertIn("12.6.1", outbound)
        self.assertIn(f"A reclamação {state.complaint_id} foi aberta", outbound)
        self.assertNotIn("cartão final", outbound)
        self.assertNotIn("foi bloqueado", outbound)

    def test_complaint_storage_failure_is_disclosed_without_false_confirmation(self):
        transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.addCleanup(transactions.close)
        gateway, _, _ = self._gateway(
            [],
            transaction_repository=transactions,
            complaint_repository=FailingComplaintRepository(),
        )
        state = gateway.calls.start("+5511999990001", call_id="call_failed_complaint")
        state = gateway.calls.confirm_language(state.call_id)
        state = gateway.calls.choose_authentication_method(state.call_id, method="phone")
        gateway.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(merchant_query="lemon"),
        )
        gateway.calls.resolve_transaction_candidate(state.call_id, confirmed=True)
        classified = gateway.calls.classify_dispute(
            state.call_id,
            allegation="DUPLICATE_PROCESSING",
            customer_reports_duplicate=True,
        )

        message = gateway._message_for(classified.state, "classification_complete")

        self.assertEqual(classified.state.complaint_filing_status, "failed")
        self.assertIsNone(classified.state.complaint_id)
        self.assertIn("Não consegui abrir a reclamação", message)
        self.assertIn("Nenhuma reclamação foi registrada", message)
        self.assertNotIn("foi aberta", message)

    async def test_ambiguous_problem_asks_for_clarification_without_code(self):
        events = [
            session_updated_event(),
            tool_call_event("confirm_language", "tool_language", {}),
            tool_call_event(
                "set_authentication_method",
                "tool_auth",
                {"method": "phone"},
            ),
            tool_call_event(
                "search_transactions",
                "tool_search",
                {"merchant_query": "lemon"},
            ),
            completed_transcript_event(speaker="customer", transcript="Sim."),
            tool_call_event(
                "confirm_transaction",
                "tool_confirm",
                {"confirmation_intent": "CONFIRM"},
            ),
            tool_call_event(
                "classify_dispute",
                "tool_classify",
                {
                    "allegation": "INSUFFICIENT_INFO",
                    "customer_denies_authorization": False,
                    "customer_reports_duplicate": False,
                },
            ),
        ]
        transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.addCleanup(transactions.close)
        gateway, websocket, _ = self._gateway(events, transaction_repository=transactions)

        await gateway.accept_and_control("call_ambiguous_classification", "+5511999990001")

        state = gateway.calls.get("call_ambiguous_classification")
        self.assertEqual(state.stage, "needs_dispute_classification")
        self.assertIsNone(state.dispute_classification.visa_condition_code)
        outbound = json.dumps(websocket.sent, ensure_ascii=False)
        self.assertIn("Não consegui distinguir", outbound)

    def test_confirmation_tool_uses_language_agnostic_intent_classes(self):
        tool = SipRealtimeGateway._transaction_confirmation_tool()
        properties = tool["parameters"]["properties"]
        intent = properties["confirmation_intent"]

        self.assertEqual(intent["enum"], ["CONFIRM", "DENY", "UNCLEAR"])
        self.assertIn("complete response", intent["description"])
        self.assertNotIn("confirmed", properties)

    def test_language_and_authentication_tools_support_unclear_intent(self):
        language = SipRealtimeGateway._language_tool()["parameters"]["properties"]
        authentication = SipRealtimeGateway._authentication_method_tool()["parameters"][
            "properties"
        ]

        self.assertIn("unclear", language["language"]["enum"])
        self.assertIn("unclear", authentication["method"]["enum"])

    def test_csat_turn_keeps_vad_response_enabled_until_survey_is_complete(self):
        transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.addCleanup(transactions.close)
        gateway, _, _ = self._gateway([], transaction_repository=transactions)
        state = gateway.calls.start("+5511999990001", call_id="call_terminal_vad")
        state = gateway.calls.confirm_language(state.call_id)
        state = gateway.calls.choose_authentication_method(state.call_id, method="phone")
        gateway.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(merchant_query="lemon"),
        )
        gateway.calls.resolve_transaction_candidate(state.call_id, confirmed=True)
        classified = gateway.calls.classify_dispute(
            state.call_id,
            allegation="DUPLICATE_PROCESSING",
            customer_reports_duplicate=True,
        )

        self.assertNotIn(
            "turn_detection", gateway._input_audio_configuration(classified.state)["input"]
        )
        completed = gateway.calls.record_csat(classified.state.call_id, rating=5)
        turn_detection = gateway._input_audio_configuration(completed)["input"]["turn_detection"]
        self.assertEqual(turn_detection["type"], "server_vad")
        self.assertFalse(turn_detection["create_response"])
        self.assertTrue(turn_detection["interrupt_response"])

    def test_required_turns_allow_phase_tool_or_explicit_human_handoff(self):
        transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.addCleanup(transactions.close)
        gateway, _, _ = self._gateway([], transaction_repository=transactions)
        state = gateway.calls.start("+5511999990001", call_id="call_tool_choice")
        self.assertEqual(gateway._tool_choice_for(state), "required")
        self.assertEqual(
            {tool["name"] for tool in gateway._tools_for(state)},
            {"set_language", "confirm_language", "request_human"},
        )

        state = gateway.calls.confirm_language(state.call_id)
        self.assertEqual(gateway._tool_choice_for(state), "required")
        self.assertEqual(
            {tool["name"] for tool in gateway._tools_for(state)},
            {"set_authentication_method", "request_human"},
        )
        state = gateway.calls.choose_authentication_method(state.call_id, method="phone")
        selection = gateway.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(merchant_query="lemon"),
        )
        self.assertEqual(gateway._tool_choice_for(selection.state), "required")
        self.assertEqual(
            {tool["name"] for tool in gateway._tools_for(selection.state)},
            {"confirm_transaction", "request_human"},
        )

        confirmed = gateway.calls.resolve_transaction_candidate(
            state.call_id,
            confirmed=True,
        )
        self.assertEqual(gateway._tool_choice_for(confirmed.state), "required")
        self.assertEqual(
            {tool["name"] for tool in gateway._tools_for(confirmed.state)},
            {"classify_dispute", "request_human"},
        )

    async def test_asr_distorted_sim_reaches_problem_classification_question(self):
        events = [
            session_updated_event(),
            tool_call_event("confirm_language", "tool_language", {}),
            tool_call_event(
                "set_authentication_method",
                "tool_auth",
                {"method": "phone"},
            ),
            tool_call_event(
                "search_transactions",
                "tool_search",
                {"city": "São Paulo"},
            ),
            completed_transcript_event(speaker="customer", transcript="Sihir."),
            tool_call_event(
                "confirm_transaction",
                "tool_confirm_transaction",
                {"confirmation_intent": "CONFIRM"},
            ),
        ]
        transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.addCleanup(transactions.close)
        gateway, websocket, _ = self._gateway(events, transaction_repository=transactions)

        await gateway.accept_and_control("call_asr_distorted_sim", "+5511999990001")

        state = gateway.calls.get("call_asr_distorted_sim")
        self.assertEqual(state.stage, "needs_dispute_classification")
        outbound = json.dumps(websocket.sent, ensure_ascii=False)
        self.assertIn("você não fez nem autorizou essa compra", outbound)
        self.assertNotIn("transação ainda não foi confirmada", outbound)

    async def test_unclear_speech_cannot_confirm_a_transaction(self):
        events = [
            session_updated_event(),
            tool_call_event("confirm_language", "tool_language", {}),
            tool_call_event(
                "set_authentication_method",
                "tool_auth",
                {"method": "phone"},
            ),
            tool_call_event(
                "search_transactions",
                "tool_search",
                {"approximate_amount": 13},
            ),
            completed_transcript_event(
                speaker="customer",
                transcript="جتين",
            ),
            tool_call_event(
                "confirm_transaction",
                "tool_false_positive",
                {"confirmation_intent": "UNCLEAR"},
            ),
        ]
        transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.addCleanup(transactions.close)
        gateway, websocket, _ = self._gateway(
            events,
            transaction_repository=transactions,
        )

        await gateway.accept_and_control(
            "call_unclear_confirmation",
            "+5511999990001",
        )

        state = gateway.calls.get("call_unclear_confirmation")
        self.assertEqual(state.stage, "confirm_transaction")
        self.assertIsNone(state.confirmed_transaction)
        outbound = json.dumps(websocket.sent, ensure_ascii=False)
        self.assertIn("transação ainda não foi confirmada", outbound)

    async def test_denial_intent_keeps_new_detail_for_reranking(self):
        events = [
            session_updated_event(),
            tool_call_event("confirm_language", "tool_language", {}),
            tool_call_event(
                "set_authentication_method",
                "tool_auth",
                {"method": "phone"},
            ),
            tool_call_event(
                "search_transactions",
                "tool_search",
                {"approximate_amount": 27, "merchant_query": "fruta"},
            ),
            completed_transcript_event(
                speaker="customer",
                transcript="Não, minha transação foi feita em Lima.",
            ),
            tool_call_event(
                "confirm_transaction",
                "tool_denial_with_city",
                {"confirmation_intent": "DENY", "city": "Lima"},
            ),
        ]
        transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.addCleanup(transactions.close)
        gateway, _, _ = self._gateway(events, transaction_repository=transactions)

        await gateway.accept_and_control(
            "call_denial_with_detail",
            "+5511999990001",
        )

        state = gateway.calls.get("call_denial_with_detail")
        self.assertEqual(state.stage, "confirm_transaction")
        self.assertIsNone(state.confirmed_transaction)
        self.assertEqual(state.transaction_criteria.city, "Lima")
        self.assertEqual(state.transaction_guess_attempts, 2)
        self.assertEqual(state.current_transaction.merchant_name, "Peach Grove Grocer")
        self.assertEqual(len(state.rejected_transaction_ids), 1)

    async def test_unsupported_amount_is_dropped_instead_of_becoming_a_filter(self):
        events = [
            session_updated_event(),
            tool_call_event("confirm_language", "tool_language", {}),
            tool_call_event(
                "set_authentication_method",
                "tool_auth",
                {"method": "phone"},
            ),
            completed_transcript_event(
                speaker="customer",
                transcript="Deixa eu ver rapidinho, tá?",
            ),
            tool_call_event(
                "search_transactions",
                "tool_invented_amount",
                {"approximate_amount": 27},
            ),
        ]
        transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.addCleanup(transactions.close)
        gateway, websocket, _ = self._gateway(events, transaction_repository=transactions)

        await gateway.accept_and_control(
            "call_invented_amount",
            "+5511999990001",
        )

        state = gateway.calls.get("call_invented_amount")
        self.assertIsNone(state.transaction_criteria.approximate_amount)
        self.assertEqual(state.stage, "needs_transaction_details")
        outbound = json.dumps(websocket.sent, ensure_ascii=False)
        self.assertNotIn("27,00", outbound)

    def test_candidate_summaries_are_voice_friendly_in_supported_languages(self):
        transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.addCleanup(transactions.close)
        gateway, _, _ = self._gateway([], transaction_repository=transactions)
        scenarios = {
            "pt": ("brazilian", "Encontrei uma possibilidade", "É essa transação?"),
            "es": ("colombian", "Encontré una posibilidad", "¿Es esa transacción?"),
            "en": ("american", "I found one possibility", "Is that the transaction?"),
        }

        for index, (language, (accent, opening, question)) in enumerate(
            scenarios.items(),
            start=1,
        ):
            with self.subTest(language=language):
                call_id = f"call_summary_{index}"
                state = gateway.calls.start("+5511999990001", call_id=call_id)
                state = gateway.calls.confirm_language(state.call_id)
                state = gateway.calls.choose_authentication_method(
                    state.call_id,
                    method="phone",
                )
                state = gateway.calls.choose_language(
                    state.call_id,
                    language=language,
                    accent=accent,
                )
                selection = gateway.calls.search_transactions(
                    state.call_id,
                    TransactionSearchCriteria(merchant_query="lemon"),
                )

                message = gateway._message_for(
                    selection.state,
                    "transaction_candidate",
                )

                self.assertIn(opening, message)
                self.assertIn(question, message)
                self.assertIn("Lemon Drop Market", message)
                self.assertNotIn("transaction_id", message)
                self.assertIn(
                    {"pt": "Filtros ativos", "es": "Filtros activos", "en": "Active filters"}[
                        language
                    ],
                    message,
                )

    def test_classification_is_voice_friendly_in_supported_languages(self):
        transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.addCleanup(transactions.close)
        gateway, _, _ = self._gateway([], transaction_repository=transactions)
        scenarios = {
            "pt": ("brazilian", "não fez nem autorizou", "processamento duplicado"),
            "es": ("colombian", "no hiciste ni autorizaste", "procesamiento duplicado"),
            "en": ("american", "not make or authorize", "duplicate processing"),
        }

        for index, (language, (accent, question_text, result_text)) in enumerate(
            scenarios.items(),
            start=1,
        ):
            with self.subTest(language=language):
                call_id = f"call_classification_{index}"
                gateway.calls.start("+5511999990001", call_id=call_id)
                gateway.calls.confirm_language(call_id)
                gateway.calls.choose_authentication_method(call_id, method="phone")
                gateway.calls.choose_language(call_id, language=language, accent=accent)
                selection = gateway.calls.search_transactions(
                    call_id,
                    TransactionSearchCriteria(merchant_query="lemon"),
                )
                confirmed = gateway.calls.resolve_transaction_candidate(
                    call_id,
                    confirmed=True,
                )
                question = gateway._message_for(
                    confirmed.state,
                    "classification_question",
                )
                classified = gateway.calls.classify_dispute(
                    call_id,
                    allegation="DUPLICATE_PROCESSING",
                    customer_reports_duplicate=True,
                )
                message = gateway._message_for(
                    classified.state,
                    "classification_complete",
                )

                self.assertEqual(
                    selection.state.current_transaction.merchant_name, "Lemon Drop Market"
                )
                self.assertIn(question_text, question)
                self.assertIn(result_text, message)
                self.assertIn("12.6.1", message)

    async def test_realtime_tool_can_remove_and_clear_transaction_filters(self):
        events = [
            session_updated_event(),
            tool_call_event("confirm_language", "tool_language", {}),
            tool_call_event(
                "set_authentication_method",
                "tool_auth",
                {"method": "phone"},
            ),
            tool_call_event(
                "search_transactions",
                "tool_initial_search",
                {
                    "merchant_query": "lemon",
                    "approximate_amount": 13,
                    "currency": "USD",
                },
            ),
            tool_call_event(
                "search_transactions",
                "tool_remove_filter",
                {"remove_filters": ["merchant_query"]},
            ),
            tool_call_event(
                "search_transactions",
                "tool_clear_filters",
                {"clear_filters": True},
            ),
        ]
        transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.addCleanup(transactions.close)
        gateway, websocket, calls = self._gateway(
            events,
            transaction_repository=transactions,
        )

        await gateway.accept_and_control(
            "call_filter_controls",
            "+5511999990001",
        )

        state = gateway.calls.get("call_filter_controls")
        self.assertEqual(state.stage, "needs_transaction_details")
        self.assertFalse(state.transaction_criteria.has_any_filter)
        search_tool = next(
            tool for tool in calls.accepted[0][1]["tools"] if tool["name"] == "search_transactions"
        )
        properties = search_tool["parameters"]["properties"]
        self.assertIn("remove_filters", properties)
        self.assertIn("clear_filters", properties)
        outbound = json.dumps(websocket.sent, ensure_ascii=False)
        self.assertIn("Ainda não há filtros ativos", outbound)

    def test_denial_asks_for_one_missing_detail_before_another_candidate(self):
        transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.addCleanup(transactions.close)
        gateway, _, _ = self._gateway([], transaction_repository=transactions)
        state = gateway.calls.start(
            "+5511999990001",
            call_id="call_refinement_question",
        )
        state = gateway.calls.confirm_language(state.call_id)
        state = gateway.calls.choose_authentication_method(state.call_id, method="phone")
        gateway.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(approximate_amount=13),
        )

        denied = gateway.calls.resolve_transaction_candidate(
            state.call_id,
            confirmed=False,
        )
        message = gateway._message_for(denied.state, "transaction_clarification")

        self.assertEqual(denied.outcome, TransactionSelectionOutcome.NEEDS_CLARIFICATION)
        self.assertIsNone(denied.state.current_transaction)
        self.assertIn("não vou usar essa opção", message)
        self.assertIn("nome do estabelecimento", message)
        self.assertNotIn("Encontrei uma possibilidade", message)

        refined = gateway.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(city="São Paulo"),
        )
        denied_again = gateway.calls.resolve_transaction_candidate(
            state.call_id,
            confirmed=False,
        )
        next_question = gateway._message_for(
            denied_again.state,
            "transaction_clarification",
        )

        self.assertEqual(refined.state.current_transaction.merchant_name, "Coconut Island Grocer")
        self.assertIn("data", next_question)
        self.assertNotIn("nome do estabelecimento", next_question)

    def test_three_denials_use_configured_handoff_availability(self):
        transactions = SQLiteTransactionSearchRepository(seed_customer_id="CLI-002")
        self.addCleanup(transactions.close)
        gateway, _, _ = self._gateway([], transaction_repository=transactions)
        state = gateway.calls.start(
            "+5511999990001",
            call_id="call_handoff_message",
        )
        state = gateway.calls.confirm_language(state.call_id)
        state = gateway.calls.choose_authentication_method(state.call_id, method="phone")
        selection = gateway.calls.search_transactions(
            state.call_id,
            TransactionSearchCriteria(merchant_query="fruit"),
        )

        for refinement in ("grapes", "peach", None):
            selection = gateway.calls.resolve_transaction_candidate(
                state.call_id,
                confirmed=False,
            )
            if refinement is not None:
                selection = gateway.calls.search_transactions(
                    state.call_id,
                    TransactionSearchCriteria(merchant_query=refinement),
                )

        unavailable = gateway._handoff_plan(selection.state)
        message = gateway._message_for(
            selection.state,
            gateway._handoff_message_reason(unavailable),
        )
        self.assertIn("não está configurado", message)

        configured, _, _ = self._gateway(
            [],
            transaction_repository=transactions,
            human_handoff_number="+5511981020050",
        )
        transferable = configured._handoff_plan(selection.state)
        message = configured._message_for(
            selection.state,
            configured._handoff_message_reason(transferable),
        )
        self.assertTrue(transferable.can_transfer)
        self.assertIn("transferir você agora", message)


if __name__ == "__main__":
    unittest.main()
