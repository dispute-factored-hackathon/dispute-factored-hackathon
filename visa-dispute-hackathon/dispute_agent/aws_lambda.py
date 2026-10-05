"""AWS Lambda ingress and on-demand worker for OpenAI Realtime SIP calls."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from typing import Any

from webapp.backend.aws_runtime import configure_application_runtime
from webapp.backend.config import get_settings
from webapp.backend.repositories.postgres import open_repositories

from .sip_realtime import SipRealtimeGateway, _value, extract_caller_phone, extract_twilio_call_sid
from .twilio_handoff import TwilioCallHandoff, TwilioHandoffCredentials
from .voice_call import voice_repository_arguments

LOGGER = logging.getLogger(__name__)


def _telemetry(event: str, *, call_id: str | None = None, **fields: Any) -> None:
    """Emit one structured JSON application event to CloudWatch."""
    payload: dict[str, Any] = {"event": event}
    if call_id is not None:
        payload["call_id"] = call_id
    payload.update(fields)
    LOGGER.info(json.dumps(payload, ensure_ascii=False, default=str))


# The Lambda invokes itself asynchronously with this mode as soon as the
# webhook has accepted the pending SIP call. The ingress invocation owns the
# time-sensitive accept decision; the worker owns the long-lived sideband.
WORKER_MODE = "control_realtime_call"

# Leave headroom below a typical 15-minute Lambda timeout.
MAX_CALL_SECONDS = 840

_gateway: SipRealtimeGateway | None = None
_repositories: Any | None = None


def _load_json_secret(
    secret_arn_env: str,
    *,
    required_keys: set[str],
    secret_name: str,
) -> dict[str, str]:
    """Load and validate one JSON secret from AWS Secrets Manager."""

    import boto3

    secret_arn = os.environ.get(secret_arn_env, "").strip()

    if not secret_arn:
        raise RuntimeError(f"{secret_arn_env} is not configured")

    started = time.monotonic()

    response = boto3.client("secretsmanager").get_secret_value(
        SecretId=secret_arn,
    )

    _telemetry(
        "aws.secret.loaded",
        secret_name=secret_name,
        duration_ms=round((time.monotonic() - started) * 1000, 2),
    )

    try:
        secret = json.loads(response["SecretString"])
    except (KeyError, json.JSONDecodeError, TypeError) as error:
        raise RuntimeError(f"{secret_name} secret is not valid JSON") from error

    if not isinstance(secret, dict):
        raise RuntimeError(f"{secret_name} secret must contain a JSON object")

    missing = required_keys.difference(secret)

    if missing:
        raise RuntimeError(f"{secret_name} secret is missing keys: {sorted(missing)}")

    return {str(key): str(value) for key, value in secret.items()}


def _load_openai_secret() -> dict[str, str]:
    """Load OpenAI API and webhook signing credentials."""

    names = {"JEV_API_KEY", "OPENAI_API_KEY", "OPENAI_WEBHOOK_SECRET"}
    configured = {name: os.environ.get(name, "").strip() for name in names}
    if all(configured.values()):
        return configured

    return _load_json_secret(
        "OPENAI_SECRET_ARN",
        required_keys=names,
        secret_name="openai",
    )


def _load_twilio_handoff() -> TwilioCallHandoff:
    """Load the least-privilege Twilio credentials used for human handoff."""

    names = {
        "TWILIO_ACCOUNT_SID",
        "TWILIO_API_KEY_SID",
        "TWILIO_API_KEY_SECRET",
        "TWILIO_CALLER_ID",
    }
    configured = {name: os.environ.get(name, "").strip() for name in names}
    if not all(configured.values()):
        configured = _load_json_secret(
            "TWILIO_SECRET_ARN",
            required_keys=names,
            secret_name="twilio",
        )
    return TwilioCallHandoff(
        TwilioHandoffCredentials(
            account_sid=configured["TWILIO_ACCOUNT_SID"],
            api_key_sid=configured["TWILIO_API_KEY_SID"],
            api_key_secret=configured["TWILIO_API_KEY_SECRET"],
            caller_id=configured["TWILIO_CALLER_ID"],
        )
    )


def _configure_langsmith() -> None:
    """Load the LangSmith API key once per Lambda execution environment."""

    if os.environ.get("LANGSMITH_API_KEY", "").strip():
        return

    secret = _load_json_secret(
        "LANGSMITH_SECRET_ARN",
        required_keys={"LANGSMITH_API_KEY"},
        secret_name="langsmith",
    )

    os.environ["LANGSMITH_API_KEY"] = secret["LANGSMITH_API_KEY"]

    _telemetry(
        "langsmith.configured",
        tracing_enabled=os.environ.get(
            "LANGSMITH_TRACING",
            "",
        )
        .strip()
        .casefold()
        in {"1", "true", "yes", "on"},
        project=os.environ.get("LANGSMITH_PROJECT", ""),
        endpoint=os.environ.get("LANGSMITH_ENDPOINT", ""),
    )


def _get_gateway() -> SipRealtimeGateway:
    """Create one gateway per warm Lambda execution environment."""

    global _gateway, _repositories

    if _gateway is None:
        started = time.monotonic()

        configure_application_runtime()
        get_settings.cache_clear()

        # Configure LangSmith before application code begins creating traced runs.
        _configure_langsmith()

        secret = _load_openai_secret()

        # Shared PostgreSQL configured with DATABASE_URL; customer data comes from the lakehouse seed.
        repositories = open_repositories(get_settings())
        _repositories = repositories
        _gateway = SipRealtimeGateway(
            repositories.customers,
            **voice_repository_arguments(repositories),
            api_key=secret["OPENAI_API_KEY"],
            webhook_secret=secret["OPENAI_WEBHOOK_SECRET"],
            jev_api_key=secret.get("JEV_API_KEY"),
            twilio_handoff=_load_twilio_handoff(),
        )

        _telemetry(
            "sip.gateway.initialized",
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            langsmith_tracing=os.environ.get(
                "LANGSMITH_TRACING",
                "",
            )
            .strip()
            .casefold()
            in {"1", "true", "yes", "on"},
            langsmith_project=os.environ.get("LANGSMITH_PROJECT", ""),
        )

    return _gateway


def _close_gateway() -> None:
    """Release database pools so warm Lambdas do not prevent Aurora auto-pause."""
    global _gateway, _repositories
    if _repositories is not None:
        _repositories.close()
    _repositories = None
    _gateway = None


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
    twilio_call_sid: str | None = None,
) -> None:
    """Invoke this Lambda asynchronously to own the Realtime sideband."""

    import boto3

    payload = {
        "mode": WORKER_MODE,
        "call_id": call_id,
        "caller_phone": caller_phone,
        "accepted": True,
        "twilio_call_sid": twilio_call_sid,
    }

    invoke_started = time.monotonic()
    _telemetry("worker.invoke.started", call_id=call_id)

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

    _telemetry(
        "worker.invoke.completed",
        call_id=call_id,
        lambda_status=status_code,
        duration_ms=round((time.monotonic() - invoke_started) * 1000, 2),
    )


def _run_worker(event: dict[str, Any]) -> dict[str, Any]:
    """Run the long-lived sideband controller for one accepted SIP call."""

    call_id = str(event.get("call_id", ""))
    caller_phone = str(event.get("caller_phone", ""))
    twilio_call_sid = str(event.get("twilio_call_sid", "")) or None

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

    worker_started = time.monotonic()
    _telemetry("worker.started", call_id=call_id)

    try:
        if not bool(event.get("accepted")):
            # Backward compatibility for queued payloads created by an older
            # deployment. New ingress invocations always accept first.
            asyncio.run(
                _get_gateway().accept_call(
                    call_id,
                    caller_phone,
                )
            )
            _telemetry("sip.accept.completed", call_id=call_id, owner="worker")
        asyncio.run(
            _get_gateway().control_call(
                call_id,
                caller_phone,
                max_duration_seconds=MAX_CALL_SECONDS,
                twilio_call_sid=twilio_call_sid,
            )
        )
    except Exception as error:
        _telemetry(
            "worker.failed",
            call_id=call_id,
            duration_ms=round((time.monotonic() - worker_started) * 1000, 2),
            error_type=type(error).__name__,
            error=str(error),
        )
        LOGGER.exception(
            "Realtime worker crashed call_id=%s",
            call_id,
        )
        raise

    _telemetry(
        "worker.completed",
        call_id=call_id,
        duration_ms=round((time.monotonic() - worker_started) * 1000, 2),
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

        _telemetry("sip.reject.completed", call_id=call_id)

    except Exception as error:
        _telemetry(
            "sip.reject.failed",
            call_id=call_id,
            error_type=type(error).__name__,
            error=str(error),
        )
        LOGGER.exception(
            "Could not reject SIP call call_id=%s; "
            "the call may already be unavailable or the event may be synthetic",
            call_id,
        )


def _dispatch_event(
    event: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    """Verify the webhook and launch the call-owning worker without blocking."""

    started = time.monotonic()

    # Internal asynchronous invocation used for the long-running call worker.
    if event.get("mode") == WORKER_MODE:
        return _run_worker(event)

    _telemetry("webhook.handler.started")

    gateway = _get_gateway()

    _telemetry(
        "webhook.gateway.ready",
        duration_ms=round((time.monotonic() - started) * 1000, 2),
    )

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

    _telemetry(
        "webhook.verified",
        duration_ms=round((time.monotonic() - started) * 1000, 2),
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
        _telemetry(
            "sip.incoming.missing_call_id",
            event_id=event_id,
        )
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

    twilio_call_sid = extract_twilio_call_sid(webhook)

    LOGGER.info(
        "Incoming SIP call event_id=%s call_id=%s caller=%s",
        event_id,
        call_id,
        caller_phone,
    )

    _telemetry(
        "sip.caller.extracted",
        call_id=call_id,
        event_id=event_id,
        duration_ms=round((time.monotonic() - started) * 1000, 2),
    )

    # Accept in the ingress invocation. The SIP decision is time-sensitive and
    # answering here gives the carrier a final response before the asynchronous
    # worker cold-starts, avoiding repeated INVITEs and silent dialing.
    try:
        asyncio.run(gateway.accept_call(call_id, caller_phone))
        _telemetry(
            "sip.accept.completed",
            call_id=call_id,
            owner="webhook",
            duration_ms=round((time.monotonic() - started) * 1000, 2),
        )
    except Exception as error:
        _telemetry(
            "sip.accept.failed",
            call_id=call_id,
            owner="webhook",
            error_type=type(error).__name__,
            error=str(error),
        )
        LOGGER.exception("Could not accept incoming SIP call call_id=%s", call_id)
        return _response(502, {"status": "call_accept_failed"})

    # The worker only owns the long-lived sideband after acceptance, keeping
    # the public webhook response bounded while preserving the answered call.

    try:
        _invoke_worker(
            context,
            call_id=call_id,
            caller_phone=caller_phone,
            twilio_call_sid=twilio_call_sid,
        )

    except Exception as error:
        _telemetry(
            "worker.invoke.failed",
            call_id=call_id,
            error_type=type(error).__name__,
            error=str(error),
        )
        LOGGER.exception(
            "Realtime worker could not be started after accept call_id=%s",
            call_id,
        )

        # A 5xx encourages webhook redelivery and gives the platform another
        # chance to start the worker when Lambda invocation itself failed.
        return _response(
            503,
            {
                "status": "worker_start_failed",
            },
        )

    _telemetry(
        "webhook.handler.completed",
        call_id=call_id,
        event_id=event_id,
        status="worker_started",
        duration_ms=round((time.monotonic() - started) * 1000, 2),
    )

    return _response(
        202,
        {
            "status": "worker_started",
        },
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Dispatch one ingress/worker invocation and always release its database pool."""
    try:
        return _dispatch_event(event, context)
    finally:
        _close_gateway()
