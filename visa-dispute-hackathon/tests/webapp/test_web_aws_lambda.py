from types import SimpleNamespace
from unittest.mock import patch

from webapp.backend import aws_lambda


def function_url_event(path: str) -> dict:
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "example.lambda-url.sa-east-1.on.aws"},
        "requestContext": {
            "accountId": "anonymous",
            "apiId": "example",
            "domainName": "example.lambda-url.sa-east-1.on.aws",
            "domainPrefix": "example",
            "http": {
                "method": "GET",
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "pytest",
            },
            "requestId": "request-1",
            "routeKey": "$default",
            "stage": "$default",
            "time": "03/Oct/2026:12:00:00 +0000",
            "timeEpoch": 1791028800000,
        },
        "isBase64Encoded": False,
    }


def lambda_context(request_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        function_name="dispute-factored-demo-web",
        function_version="$LATEST",
        invoked_function_arn=(
            "arn:aws:lambda:sa-east-1:123456789012:function:dispute-factored-demo-web"
        ),
        memory_limit_in_mb="512",
        aws_request_id=request_id,
        log_group_name="/aws/lambda/dispute-factored-demo-web",
        log_stream_name="test",
    )


def stub_adapter(body: str):
    def adapter(event, context):
        del event, context
        return {"statusCode": 200, "body": body}

    return adapter


def test_function_url_serves_health_endpoint():
    adapter = stub_adapter('{"status":"ok"}')
    with patch.object(aws_lambda, "_get_adapter", return_value=adapter):
        response = aws_lambda.lambda_handler(
            function_url_event("/health"), lambda_context("request-1")
        )

    assert response["statusCode"] == 200
    assert '"status":"ok"' in response["body"]


def test_function_url_serves_login_page():
    adapter = stub_adapter("Factored Bank")
    with patch.object(aws_lambda, "_get_adapter", return_value=adapter):
        response = aws_lambda.lambda_handler(
            function_url_event("/login"), lambda_context("request-2")
        )

    assert response["statusCode"] == 200
    assert "Factored Bank" in response["body"]
