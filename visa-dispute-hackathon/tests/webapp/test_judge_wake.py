import io
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from webapp.backend import judge_wake


class FakeEc2:
    def __init__(self, state: str, *, launch_time: datetime | None = None) -> None:
        self.state = state
        self.launch_time = launch_time
        self.started: list[list[str]] = []
        self.stopped: list[list[str]] = []

    def describe_instances(self, *, InstanceIds):
        instance = {"State": {"Name": self.state}}
        if self.launch_time:
            instance["LaunchTime"] = self.launch_time
        return {"Reservations": [{"Instances": [instance]}]}

    def start_instances(self, *, InstanceIds):
        self.started.append(InstanceIds)

    def stop_instances(self, *, InstanceIds):
        self.stopped.append(InstanceIds)


class FakeLambda:
    def __init__(self, warmed: bool = True) -> None:
        self.warmed = warmed

    def invoke(self, **kwargs):
        assert json.loads(kwargs["Payload"]) == {"warmup": True}
        return {
            "StatusCode": 200,
            "Payload": io.BytesIO(json.dumps({"warmed": self.warmed}).encode()),
        }


class FakeCloudWatch:
    def __init__(self, invocation_counts: list[float]) -> None:
        self.invocation_counts = iter(invocation_counts)

    def get_metric_statistics(self, **kwargs):
        assert kwargs["MetricName"] == "Invocations"
        return {"Datapoints": [{"Sum": next(self.invocation_counts)}]}


def settings() -> dict[str, str]:
    return {
        "EGRESS_INSTANCE_ID": "i-test",
        "WEB_FUNCTION_NAME": "demo-web",
        "VOICE_FUNCTION_NAME": "demo-sip",
        "APPLICATION_URL": "https://app.example/",
        "IDLE_MINUTES": "30",
    }


def test_wake_starts_a_stopped_egress_instance():
    ec2 = FakeEc2("stopped")
    with (
        patch.dict("os.environ", settings(), clear=True),
        patch.object(judge_wake, "_client", return_value=ec2),
    ):
        response = judge_wake.lambda_handler({}, None)

    assert json.loads(response["body"])["state"] == "starting"
    assert ec2.started == [["i-test"]]


def test_wake_returns_application_url_after_web_warmup():
    clients = {"ec2": FakeEc2("running"), "lambda": FakeLambda()}
    with (
        patch.dict("os.environ", settings(), clear=True),
        patch.object(judge_wake, "_client", side_effect=clients.__getitem__),
    ):
        response = judge_wake.lambda_handler({}, None)

    assert json.loads(response["body"]) == {
        "ready": True,
        "state": "ready",
        "application_url": "https://app.example/",
    }


def test_idle_check_keeps_egress_running_during_recent_web_or_voice_activity():
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    ec2 = FakeEc2("running", launch_time=now - timedelta(hours=2))
    clients = {
        "ec2": ec2,
        "cloudwatch": FakeCloudWatch([1, 0]),
    }
    with (
        patch.dict("os.environ", settings(), clear=True),
        patch.object(judge_wake, "_client", side_effect=clients.__getitem__),
    ):
        result = judge_wake._idle_check(now)

    assert result["reason"] == "recent_activity"
    assert ec2.stopped == []


def test_idle_check_stops_egress_after_web_and_voice_are_idle():
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    ec2 = FakeEc2("running", launch_time=now - timedelta(hours=2))
    clients = {
        "ec2": ec2,
        "cloudwatch": FakeCloudWatch([0, 0]),
    }
    with (
        patch.dict("os.environ", settings(), clear=True),
        patch.object(judge_wake, "_client", side_effect=clients.__getitem__),
    ):
        result = judge_wake._idle_check(now)

    assert result == {"status": "stopping", "reason": "idle"}
    assert ec2.stopped == [["i-test"]]


def test_idle_check_fails_safe_when_activity_cannot_be_read():
    now = datetime(2026, 10, 8, 12, tzinfo=UTC)
    ec2 = FakeEc2("running", launch_time=now - timedelta(hours=2))

    def client(name: str):
        if name == "ec2":
            return ec2
        raise RuntimeError("CloudWatch unavailable")

    with (
        patch.dict("os.environ", settings(), clear=True),
        patch.object(judge_wake, "_client", side_effect=client),
    ):
        result = judge_wake._idle_check(now)

    assert result == {"status": "kept_running", "reason": "activity_check_failed"}
    assert ec2.stopped == []
