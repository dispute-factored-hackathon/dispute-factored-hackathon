from types import SimpleNamespace

from webapp.backend.aws_lambda import lambda_handler


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


def test_function_url_serves_health_endpoint():
    response = lambda_handler(function_url_event("/health"), lambda_context("request-1"))

    assert response["statusCode"] == 200
    assert '"status":"ok"' in response["body"]


def test_function_url_serves_login_page():
    response = lambda_handler(function_url_event("/login"), lambda_context("request-2"))

    assert response["statusCode"] == 200
    assert "Factored Bank" in response["body"]
