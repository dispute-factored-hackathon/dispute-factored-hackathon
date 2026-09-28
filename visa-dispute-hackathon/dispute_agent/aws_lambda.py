"""AWS Lambda ingress and on-demand worker for OpenAI Realtime SIP calls."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

from .sip_realtime import SipRealtimeGateway, _value, extract_caller_phone

LOGGER = logging.getLogger(__name__)

DEFAULT_CUSTOMERS = Path(__file__).parents[1] / "demo_data" / "customers.csv"

# The Lambda invokes itself asynchronously with this mode after the webhook
# invocation has accepted the SIP call.
WORKER_MODE = "control_realtime_call"

# Leave headroom below a typical 15-minute Lambda timeout.
MAX_CALL_SECONDS = 840

_gateway: SipRealtimeGateway | None = None


def _load_secret() -> dict[str, str]:
    """Load the OpenAI API key and webhook secret from AWS Secrets Manager."""

    import boto3

    secret_arn = os.environ["OPENAI_SECRET_ARN"]

    response = boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)

    secret = json.loads(response["SecretString"])

    required = {
        "OPENAI_API_KEY",
        "OPENAI_WEBHOOK_SECRET",
    }

    missing = required.difference(secret)

    if missing:
        raise RuntimeError(f"OpenAI secret is missing keys: {sorted(missing)}")

    return secret


def _get_gateway() -> SipRealtimeGateway:
    """Create one gateway per warm Lambda execution environment."""

    global _gateway

    if _gateway is None:
        secret = _load_secret()

        _gateway = SipRealtimeGateway(
            os.getenv(
                "CUSTOMERS_CSV",
                str(DEFAULT_CUSTOMERS),
            ),
            api_key=secret["OPENAI_API_KEY"],
            webhook_secret=secret["OPENAI_WEBHOOK_SECRET"],
        )

    return _gateway


def _response(
    status_code: int,
    payload: dict[str, str],
) -> dict[str, Any]:
    """Build an AWS Lambda Function URL HTTP response."""

    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
        },
        "body": json.dumps(payload),
    }


def _raw_body(event: dict[str, Any]) -> bytes:
    """Return the original HTTP request body used for webhook verification."""

    body = event.get("body", "")

    if event.get("isBase64Encoded"):
        return base64.b64decode(body)

    if isinstance(body, bytes):
        return body

    return str(body).encode("utf-8")


def _invoke_worker(
    context: Any,
    *,
    call_id: str,
    caller_phone: str,
) -> None:
    """Invoke this Lambda asynchronously to own the Realtime sideband."""

    import boto3

    payload = {
        "mode": WORKER_MODE,
        "call_id": call_id,
        "caller_phone": caller_phone,
    }

    LOGGER.info(
        "Invoking Realtime worker call_id=%s caller=%s",
        call_id,
        caller_phone,
    )

    response = boto3.client("lambda").invoke(
        FunctionName=context.invoked_function_arn,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8"),
    )

    status_code = int(response.get("StatusCode", 0))

    if status_code not in {200, 202}:
        raise RuntimeError(
            f"Failed to invoke Realtime worker for call {call_id}: Lambda status {status_code}"
        )

    LOGGER.info(
        "Realtime worker invocation queued call_id=%s lambda_status=%s",
        call_id,
        status_code,
    )


def _run_worker(event: dict[str, Any]) -> dict[str, Any]:
    """Run the long-lived sideband controller for one accepted SIP call."""

    call_id = str(event.get("call_id", ""))
    caller_phone = str(event.get("caller_phone", ""))

    if not call_id:
        LOGGER.error("Realtime worker invoked without call_id")
        return {
            "status": "missing_call_id",
        }

    if not caller_phone:
        LOGGER.error(
            "Realtime worker invoked without caller_phone call_id=%s",
            call_id,
        )
        return {
            "status": "missing_caller_phone",
        }

    LOGGER.info(
        "Starting Realtime sideband worker call_id=%s caller=%s",
        call_id,
        caller_phone,
    )

    try:
        asyncio.run(
            _get_gateway().control_call(
                call_id,
                caller_phone,
                max_duration_seconds=MAX_CALL_SECONDS,
            )
        )
    except Exception:
        LOGGER.exception(
            "Realtime worker crashed call_id=%s",
            call_id,
        )
        raise

    LOGGER.info(
        "Realtime sideband worker finished call_id=%s",
        call_id,
    )

    return {
        "status": "call_finished",
    }


def _safe_reject(
    gateway: SipRealtimeGateway,
    call_id: str,
) -> None:
    """Best-effort rejection.

    OpenAI test webhook events may contain a synthetic call_id that does not
    represent a live SIP call. In that case /reject can return 404. Rejection
    failure must not crash the Lambda and turn the webhook response into 502.
    """

    try:
        asyncio.run(
            asyncio.to_thread(
                gateway.client.realtime.calls.reject,
                call_id,
            )
        )

        LOGGER.info(
            "Rejected incoming SIP call call_id=%s",
            call_id,
        )

    except Exception:
        LOGGER.exception(
            "Could not reject SIP call call_id=%s; "
            "the call may already be unavailable or the event may be synthetic",
            call_id,
        )


def lambda_handler(
    event: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    """Verify the webhook, accept the SIP call, and launch its sideband worker."""

    # Internal asynchronous invocation used for the long-running call worker.
    if event.get("mode") == WORKER_MODE:
        return _run_worker(event)

    gateway = _get_gateway()

    # ------------------------------------------------------------------
    # 1. Verify the OpenAI webhook signature.
    # ------------------------------------------------------------------

    try:
        webhook = gateway.client.webhooks.unwrap(
            _raw_body(event),
            event.get("headers", {}),
        )

    except Exception:
        LOGGER.exception("OpenAI webhook signature verification failed")

        return _response(
            400,
            {
                "status": "invalid_webhook_signature",
            },
        )

    event_type = str(
        _value(
            webhook,
            "type",
            "",
        )
    )

    event_id = str(
        _value(
            webhook,
            "id",
            "",
        )
    )

    LOGGER.info(
        "Received OpenAI webhook event_id=%s type=%s",
        event_id,
        event_type,
    )

    # This service handles the Realtime SIP webhook contract.
    if event_type != "realtime.call.incoming":
        return _response(
            200,
            {
                "status": "ignored",
            },
        )

    # ------------------------------------------------------------------
    # 2. Extract the Realtime SIP call ID.
    # ------------------------------------------------------------------

    data = _value(
        webhook,
        "data",
        {},
    )

    call_id = str(
        _value(
            data,
            "call_id",
            "",
        )
    )

    if not call_id:
        LOGGER.warning(
            "Incoming Realtime SIP webhook has no call_id event_id=%s",
            event_id,
        )

        return _response(
            422,
            {
                "status": "missing_call_id",
            },
        )

    # ------------------------------------------------------------------
    # 3. Extract the caller from the SIP From header.
    # ------------------------------------------------------------------

    try:
        caller_phone = extract_caller_phone(webhook)

    except ValueError:
        LOGGER.warning(
            "Incoming SIP call has no usable caller phone event_id=%s call_id=%s",
            event_id,
            call_id,
        )

        _safe_reject(
            gateway,
            call_id,
        )

        return _response(
            422,
            {
                "status": "missing_caller_phone",
            },
        )

    LOGGER.info(
        "Incoming SIP call event_id=%s call_id=%s caller=%s",
        event_id,
        call_id,
        caller_phone,
    )

    # ------------------------------------------------------------------
    # 4. Accept the call synchronously.
    #
    # OpenAI makes the first accept/reject decision authoritative.
    # Therefore a redelivered webhook normally gets a 404/other failure
    # when trying to accept an already-decided call. We intentionally do
    # NOT start another worker in that case.
    # ------------------------------------------------------------------

    try:
        asyncio.run(
            gateway.accept_call(
                call_id,
                caller_phone,
            )
        )

    except Exception:
        LOGGER.exception(
            "SIP call could not be accepted; "
            "it may already have been decided or become unavailable "
            "event_id=%s call_id=%s",
            event_id,
            call_id,
        )

        # Return 200 so OpenAI does not keep redelivering an event whose
        # call has already been accepted/rejected or is no longer live.
        return _response(
            200,
            {
                "status": "already_decided_or_unavailable",
            },
        )

    LOGGER.info(
        "SIP call accepted event_id=%s call_id=%s",
        event_id,
        call_id,
    )

    # ------------------------------------------------------------------
    # 5. Start a separate asynchronous Lambda invocation for the
    # long-running sideband WebSocket.
    # ------------------------------------------------------------------

    try:
        _invoke_worker(
            context,
            call_id=call_id,
            caller_phone=caller_phone,
        )

    except Exception:
        LOGGER.exception(
            "Call was accepted but Realtime worker could not be started call_id=%s",
            call_id,
        )

        # The SIP call is already accepted at this point. Returning a 5xx
        # would encourage webhook redelivery, but a redelivery cannot safely
        # accept the same call again. Log the infrastructure failure and
        # acknowledge the webhook instead.
        return _response(
            200,
            {
                "status": "accepted_worker_start_failed",
            },
        )

    return _response(
        202,
        {
            "status": "accepted",
        },
    )
