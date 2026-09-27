"""AWS Lambda ingress and on-demand worker for OpenAI Realtime SIP calls."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
from typing import Any

from .sip_realtime import SipRealtimeGateway, _value, extract_caller_phone

DEFAULT_CUSTOMERS = Path(__file__).parents[1] / "demo_data" / "customers.csv"
WORKER_MODE = "control_realtime_call"
MAX_CALL_SECONDS = 840
_gateway: SipRealtimeGateway | None = None


def _load_secret() -> dict[str, str]:
    import boto3

    secret_arn = os.environ["OPENAI_SECRET_ARN"]
    response = boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)
    secret = json.loads(response["SecretString"])
    required = {"OPENAI_API_KEY", "OPENAI_WEBHOOK_SECRET"}
    missing = required.difference(secret)
    if missing:
        raise RuntimeError(f"OpenAI secret is missing keys: {sorted(missing)}")
    return secret


def _get_gateway() -> SipRealtimeGateway:
    global _gateway
    if _gateway is None:
        secret = _load_secret()
        _gateway = SipRealtimeGateway(
            os.getenv("CUSTOMERS_CSV", str(DEFAULT_CUSTOMERS)),
            api_key=secret["OPENAI_API_KEY"],
            webhook_secret=secret["OPENAI_WEBHOOK_SECRET"],
        )
    return _gateway


def _response(status_code: int, payload: dict[str, str]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload),
    }


def _raw_body(event: dict[str, Any]) -> bytes:
    body = event.get("body", "")
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    return body.encode("utf-8")


def _invoke_worker(context: Any, *, call_id: str, caller_phone: str) -> None:
    import boto3

    boto3.client("lambda").invoke(
        FunctionName=context.invoked_function_arn,
        InvocationType="Event",
        Payload=json.dumps(
            {"mode": WORKER_MODE, "call_id": call_id, "caller_phone": caller_phone}
        ).encode(),
    )


def _run_worker(event: dict[str, Any]) -> dict[str, Any]:
    asyncio.run(
        _get_gateway().control_call(
            event["call_id"],
            event["caller_phone"],
            max_duration_seconds=MAX_CALL_SECONDS,
        )
    )
    return {"status": "call_finished"}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Verify and accept the webhook, then invoke this function as its call worker."""

    if event.get("mode") == WORKER_MODE:
        return _run_worker(event)

    gateway = _get_gateway()
    try:
        webhook = gateway.client.webhooks.unwrap(_raw_body(event), event.get("headers", {}))
    except Exception:
        return _response(400, {"status": "invalid_webhook_signature"})
    if str(_value(webhook, "type", "")) != "realtime.call.incoming":
        return _response(200, {"status": "ignored"})
    data = _value(webhook, "data", {})
    call_id = str(_value(data, "call_id", ""))
    if not call_id:
        return _response(422, {"status": "missing_call_id"})
    try:
        caller_phone = extract_caller_phone(webhook)
    except ValueError:
        asyncio.run(asyncio.to_thread(gateway.client.realtime.calls.reject, call_id))
        return _response(422, {"status": "missing_caller_phone"})

    try:
        asyncio.run(gateway.accept_call(call_id, caller_phone))
    except Exception:
        # OpenAI makes the first accept/reject decision authoritative. A retried
        # webhook therefore does not start a second worker.
        return _response(200, {"status": "already_decided_or_unavailable"})
    _invoke_worker(context, call_id=call_id, caller_phone=caller_phone)
    return _response(202, {"status": "accepted"})
