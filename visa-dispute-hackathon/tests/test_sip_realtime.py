import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from dispute_agent.sip_realtime import (
    SipRealtimeGateway,
    _explicit_confirmation_from_transcript,
    create_sip_app,
    extract_caller_phone,
)
from dispute_agent.transaction_search import (
    SQLiteTransactionSearchRepository,
    TransactionSearchCriteria,
)
from dispute_agent.voice_call import TransactionSelectionOutcome

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
    def _gateway(events, *, transaction_repository=None):
        websocket = FakeWebsocket(events)
        calls = FakeAcceptCalls()
        client = SimpleNamespace(realtime=SimpleNamespace(calls=calls))
        gateway = SipRealtimeGateway(
            FIXTURE,
            api_key="sk-test",
            openai_client=client,
            websocket_connect=FakeConnector(websocket),
            transaction_repository=transaction_repository,
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
            "Language changed. We can continue your card dispute in this language.",
            outbound,
        )
        self.assertNotIn(
            "would you prefer to authenticate using the phone number",
            outbound,
        )

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
                {"confirmed": True},
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
        self.assertEqual(state.stage, "dispute_classified")
        self.assertEqual(state.confirmed_transaction.merchant_name, "Lemon Drop Market")
        self.assertEqual(state.dispute_classification.visa_condition_code, "10.4")

        configured_tools = {tool["name"] for tool in calls.accepted[0][1]["tools"]}
        self.assertIn("search_transactions", configured_tools)
        self.assertIn("confirm_transaction", configured_tools)
        self.assertIn("classify_dispute", configured_tools)

        outbound = json.dumps(websocket.sent, ensure_ascii=False)
        self.assertIn("Lemon Drop Market", outbound)
        self.assertIn("12,49", outbound)
        self.assertIn("não fez nem autorizou", outbound)
        self.assertIn("código Visa candidato é 10.4", outbound)
        self.assertNotIn("SELECT", outbound)
        self.assertNotIn(state.confirmed_transaction.transaction_id, outbound)

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
                {"confirmed": True},
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
        outbound = json.dumps(websocket.sent, ensure_ascii=False)
        self.assertIn("processamento duplicado", outbound)
        self.assertIn("12.6.1", outbound)

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
            tool_call_event("confirm_transaction", "tool_confirm", {"confirmed": True}),
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

    def test_confirmation_guard_requires_unambiguous_speech(self):
        self.assertIs(_explicit_confirmation_from_transcript("Sim."), True)
        self.assertIs(_explicit_confirmation_from_transcript("Sí, es esa."), True)
        self.assertIs(_explicit_confirmation_from_transcript("Não, foi em Lima."), False)
        self.assertIs(_explicit_confirmation_from_transcript("No, that is wrong."), False)
        self.assertIsNone(_explicit_confirmation_from_transcript("جتين"))
        self.assertIsNone(_explicit_confirmation_from_transcript("talvez"))

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
                {"confirmed": True},
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

    async def test_denial_overrides_model_and_keeps_new_detail_for_reranking(self):
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
                {"confirmed": True, "city": "Lima"},
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

    def test_three_denials_explain_that_human_handoff_is_unavailable(self):
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

        message = gateway._message_for(selection.state, "transaction_handoff")
        self.assertIn("Filtros usados na última busca", message)
        self.assertIn("atendentes humanos não estão disponíveis", message)
        self.assertIn("fora do escopo desta demonstração", message)


if __name__ == "__main__":
    unittest.main()
