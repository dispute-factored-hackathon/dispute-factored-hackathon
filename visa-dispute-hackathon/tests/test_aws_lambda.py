import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fakes import new_repositories

from dispute_agent import aws_lambda
from dispute_agent.sip_realtime import extract_twilio_call_sid
from dispute_agent.transaction_search import RepositoryTransactionSearch


class FakeWebhooks:
    def __init__(self, event=None, *, invalid=False):
        self.event = event
        self.invalid = invalid

    def unwrap(self, body, headers):
        if self.invalid:
            raise ValueError("invalid")
        return self.event


class FakeCalls:
    def __init__(self):
        self.rejected = []

    def reject(self, call_id):
        self.rejected.append(call_id)


class FakeGateway:
    def __init__(self, event=None, *, invalid=False):
        self.accepted = []
        self.controlled = []

        self.calls = FakeCalls()
        self.client = SimpleNamespace(
            webhooks=FakeWebhooks(event, invalid=invalid),
            realtime=SimpleNamespace(calls=self.calls),
        )

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
        twilio_call_sid: str | None = None,
    ) -> None:
        self.controlled.append(
            (
                call_id,
                caller_phone,
                max_duration_seconds,
                twilio_call_sid,
            )
        )


def incoming_event(include_phone=True):
    headers = (
        [{"name": "From", "value": "sip:+5511999990001@sip.example.com"}] if include_phone else []
    )
    return {
        "type": "realtime.call.incoming",
        "data": {"call_id": "call_aws", "sip_headers": headers},
    }


class AwsLambdaTests(unittest.TestCase):
    def setUp(self):
        self.context = SimpleNamespace(invoked_function_arn="arn:aws:lambda:test:function:sip")

    def tearDown(self):
        aws_lambda._close_gateway()

    def test_gateway_uses_the_shared_postgres_repositories_without_seeding(self):
        gateway = object()
        repositories = new_repositories()
        with (
            patch.object(aws_lambda, "configure_application_runtime"),
            patch.object(aws_lambda, "_configure_langsmith"),
            patch.object(aws_lambda, "open_repositories", return_value=repositories),
            patch.object(aws_lambda, "_load_twilio_handoff", return_value=object()),
            patch.object(
                aws_lambda,
                "_load_openai_secret",
                return_value={
                    "OPENAI_API_KEY": "test-key",
                    "OPENAI_WEBHOOK_SECRET": "test-secret",
                    "JEV_API_KEY": "jev-test-key",
                },
            ),
            patch.object(
                aws_lambda,
                "SipRealtimeGateway",
                return_value=gateway,
            ) as gateway_type,
        ):
            resolved = aws_lambda._get_gateway()

        self.assertIs(resolved, gateway)
        arguments = gateway_type.call_args
        self.assertIs(arguments.args[0], repositories.customers)
        self.assertIs(arguments.kwargs["complaint_repository"], repositories.complaints)
        self.assertIsInstance(
            arguments.kwargs["transaction_repository"], RepositoryTransactionSearch
        )
        self.assertIs(
            arguments.kwargs["transaction_repository"].transactions, repositories.transactions
        )
        self.assertEqual(arguments.kwargs["jev_api_key"], "jev-test-key")
        self.assertIsNotNone(arguments.kwargs["twilio_handoff"])
        # Regression: a hardcoded demo customer used to be seeded on every cold start.
        self.assertEqual(repositories.customers.search_by_full_name("", limit=10), [])

    def test_valid_webhook_accepts_before_starting_worker(self):
        gateway = FakeGateway(incoming_event())
        request = {"body": "{}", "headers": {"webhook-signature": "test"}}

        with (
            patch.object(aws_lambda, "_get_gateway", return_value=gateway),
            patch.object(aws_lambda, "_invoke_worker") as invoke_worker,
        ):
            response = aws_lambda.lambda_handler(request, self.context)

        self.assertEqual(response["statusCode"], 202)
        self.assertEqual(gateway.accepted, [("call_aws", "+5511999990001")])
        invoke_worker.assert_called_once_with(
            self.context,
            call_id="call_aws",
            caller_phone="+5511999990001",
            twilio_call_sid=None,
        )

    def test_invalid_signature_has_no_side_effect(self):
        gateway = FakeGateway(invalid=True)
        with (
            patch.object(aws_lambda, "_get_gateway", return_value=gateway),
            patch.object(aws_lambda, "_invoke_worker") as invoke_worker,
        ):
            response = aws_lambda.lambda_handler({"body": "{}"}, self.context)

        self.assertEqual(response["statusCode"], 400)
        self.assertEqual(gateway.accepted, [])
        invoke_worker.assert_not_called()

    def test_missing_phone_rejects_call(self):
        gateway = FakeGateway(incoming_event(include_phone=False))
        with patch.object(aws_lambda, "_get_gateway", return_value=gateway):
            response = aws_lambda.lambda_handler({"body": "{}"}, self.context)

        self.assertEqual(response["statusCode"], 422)
        self.assertEqual(gateway.client.realtime.calls.rejected, ["call_aws"])

    def test_worker_has_bounded_call_duration(self):
        gateway = FakeGateway()
        event = {
            "mode": aws_lambda.WORKER_MODE,
            "call_id": "call_aws",
            "caller_phone": "+5511999990001",
            "accepted": True,
        }
        with patch.object(aws_lambda, "_get_gateway", return_value=gateway):
            response = aws_lambda.lambda_handler(event, self.context)

        self.assertEqual(response, {"status": "call_finished"})
        self.assertEqual(gateway.accepted, [])
        self.assertEqual(
            gateway.controlled,
            [("call_aws", "+5511999990001", aws_lambda.MAX_CALL_SECONDS, None)],
        )

    def test_worker_accepts_legacy_payload_before_control(self):
        gateway = FakeGateway()
        event = {
            "mode": aws_lambda.WORKER_MODE,
            "call_id": "call_aws",
            "caller_phone": "+5511999990001",
        }
        with patch.object(aws_lambda, "_get_gateway", return_value=gateway):
            response = aws_lambda.lambda_handler(event, self.context)

        self.assertEqual(response, {"status": "call_finished"})
        self.assertEqual(gateway.accepted, [("call_aws", "+5511999990001")])
        self.assertEqual(
            gateway.controlled,
            [("call_aws", "+5511999990001", aws_lambda.MAX_CALL_SECONDS, None)],
        )

    def test_extracts_twilio_call_sid_from_sip_headers(self):
        event = incoming_event()
        event["data"]["sip_headers"].append({"name": "X-Twilio-CallSid", "value": "CA" + "a" * 32})

        self.assertEqual(extract_twilio_call_sid(event), "CA" + "a" * 32)

    def test_base64_function_url_body_is_decoded(self):
        encoded = "eyJvYmplY3QiOiAiZXZlbnQifQ=="
        self.assertEqual(
            json.loads(aws_lambda._raw_body({"body": encoded, "isBase64Encoded": True})),
            {"object": "event"},
        )


if __name__ == "__main__":
    unittest.main()
