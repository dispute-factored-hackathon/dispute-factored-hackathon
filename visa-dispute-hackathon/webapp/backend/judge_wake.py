"""Wake the low-cost demo environment only while a judge is using it.

The controller runs outside the application VPC.  A public Function URL starts the small
egress EC2 instance and warms the web Lambda; an EventBridge invocation stops the instance
after both the web and voice functions have been idle for the configured interval.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def _client(service_name: str) -> Any:
    """Create an AWS client lazily so unit tests do not require the AWS SDK."""

    import boto3

    return boto3.client(service_name)


def _required_setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required setting: {name}")
    return value


def _instance(ec2: Any, instance_id: str) -> dict[str, Any]:
    reservations = ec2.describe_instances(InstanceIds=[instance_id]).get("Reservations", [])
    instances = [instance for reservation in reservations for instance in reservation["Instances"]]
    if len(instances) != 1:
        raise RuntimeError("The configured egress instance was not found")
    return instances[0]


def _warm_web(lambda_client: Any, function_name: str) -> bool:
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps({"warmup": True}).encode(),
    )
    if response.get("FunctionError") or response.get("StatusCode") != 200:
        return False
    payload = response["Payload"].read()
    return json.loads(payload or b"{}").get("warmed") is True


def _recent_invocations(
    cloudwatch: Any,
    function_name: str,
    *,
    now: datetime,
    idle_minutes: int,
) -> float:
    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/Lambda",
        MetricName="Invocations",
        Dimensions=[{"Name": "FunctionName", "Value": function_name}],
        StartTime=now - timedelta(minutes=idle_minutes),
        EndTime=now,
        Period=300,
        Statistics=["Sum"],
    )
    return sum(float(point.get("Sum", 0)) for point in response.get("Datapoints", []))


def _wake() -> dict[str, Any]:
    instance_id = _required_setting("EGRESS_INSTANCE_ID")
    web_function = _required_setting("WEB_FUNCTION_NAME")
    application_url = _required_setting("APPLICATION_URL")
    ec2 = _client("ec2")
    instance = _instance(ec2, instance_id)
    state = instance["State"]["Name"]

    if state == "stopped":
        ec2.start_instances(InstanceIds=[instance_id])
        return {"ready": False, "state": "starting", "retry_after_seconds": 5}
    if state != "running":
        return {"ready": False, "state": state, "retry_after_seconds": 5}

    try:
        ready = _warm_web(_client("lambda"), web_function)
    except Exception:
        logger.exception("Web warm-up is not ready yet")
        ready = False

    if not ready:
        return {"ready": False, "state": "warming", "retry_after_seconds": 5}
    return {
        "ready": True,
        "state": "ready",
        "application_url": application_url,
    }


def _idle_check(now: datetime | None = None) -> dict[str, Any]:
    instance_id = _required_setting("EGRESS_INSTANCE_ID")
    idle_minutes = int(os.environ.get("IDLE_MINUTES", "30"))
    web_function = _required_setting("WEB_FUNCTION_NAME")
    voice_function = _required_setting("VOICE_FUNCTION_NAME")
    ec2 = _client("ec2")
    instance = _instance(ec2, instance_id)

    if instance["State"]["Name"] != "running":
        return {"status": "already_inactive"}

    checked_at = now or datetime.now(UTC)
    launch_time = instance.get("LaunchTime")
    if launch_time and checked_at - launch_time < timedelta(minutes=idle_minutes):
        return {"status": "kept_running", "reason": "minimum_uptime"}

    try:
        cloudwatch = _client("cloudwatch")
        invocations = sum(
            _recent_invocations(
                cloudwatch,
                function_name,
                now=checked_at,
                idle_minutes=idle_minutes,
            )
            for function_name in (web_function, voice_function)
        )
    except Exception:
        logger.exception("Activity lookup failed; keeping egress available")
        return {"status": "kept_running", "reason": "activity_check_failed"}

    if invocations > 0:
        return {
            "status": "kept_running",
            "reason": "recent_activity",
            "invocations": invocations,
        }

    ec2.stop_instances(InstanceIds=[instance_id])
    return {"status": "stopping", "reason": "idle"}


def _http_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store",
        },
        "body": json.dumps(payload),
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle a browser wake request or the scheduled idle check."""

    del context
    if event.get("action") == "idle_check":
        return _idle_check()
    return _http_response(_wake())
