import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from dispute_agent import aws_lambda


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
    ) -> None:
        self.controlled.append(
            (
                call_id,
                caller_phone,
                max_duration_seconds,
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
        aws_lambda._gateway = None

    def test_gateway_uses_shared_mock_backend(self):
        gateway = object()
        with (
            patch.object(aws_lambda, "_configure_langsmith"),
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
        customer_source = gateway_type.call_args.args[0]
        customer = customer_source.get_by_phone("+5511981020050")
        self.assertIsNotNone(customer)
        self.assertEqual(customer.document_number, "123456")
        self.assertEqual(customer.first_name, "Gabriel")
        self.assertEqual(customer.last_name, "Silveira")
        self.assertEqual(gateway_type.call_args.kwargs["jev_api_key"], "jev-test-key")

    def test_valid_webhook_returns_before_worker_accepts_call(self):
        gateway = FakeGateway(incoming_event())
        request = {"body": "{}", "headers": {"webhook-signature": "test"}}

        with (
            patch.object(aws_lambda, "_get_gateway", return_value=gateway),
            patch.object(aws_lambda, "_invoke_worker") as invoke_worker,
        ):
            response = aws_lambda.lambda_handler(request, self.context)

        self.assertEqual(response["statusCode"], 202)
        self.assertEqual(gateway.accepted, [])
        invoke_worker.assert_called_once_with(
            self.context,
            call_id="call_aws",
            caller_phone="+5511999990001",
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
        }
        with patch.object(aws_lambda, "_get_gateway", return_value=gateway):
            response = aws_lambda.lambda_handler(event, self.context)

        self.assertEqual(response, {"status": "call_finished"})
        self.assertEqual(gateway.accepted, [("call_aws", "+5511999990001")])
        self.assertEqual(
            gateway.controlled,
            [("call_aws", "+5511999990001", aws_lambda.MAX_CALL_SECONDS)],
        )

    def test_base64_function_url_body_is_decoded(self):
        encoded = "eyJvYmplY3QiOiAiZXZlbnQifQ=="
        self.assertEqual(
            json.loads(aws_lambda._raw_body({"body": encoded, "isBase64Encoded": True})),
            {"object": "event"},
        )


if __name__ == "__main__":
    unittest.main()
