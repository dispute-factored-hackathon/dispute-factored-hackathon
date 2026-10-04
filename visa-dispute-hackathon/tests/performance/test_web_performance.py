"""Performance budgets that protect the lightweight public application shell."""

from __future__ import annotations

import json
import subprocess
import sys
import time

from fastapi.testclient import TestClient

from scripts.performance_smoke import percentile
from webapp.backend.main import app


def test_public_shell_import_stays_lazy_and_under_budget():
    code = """
import json, sys, time
started = time.perf_counter()
import webapp.backend.main
print(json.dumps({
    "elapsed": time.perf_counter() - started,
    "alembic": "alembic" in sys.modules,
    "langgraph": "langgraph" in sys.modules,
    "openai": "openai" in sys.modules,
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    result = json.loads(completed.stdout)
    assert result["elapsed"] < 3.0
    assert result["alembic"] is False
    assert result["langgraph"] is False
    assert result["openai"] is False


def test_warm_public_shell_p95_stays_under_local_budget():
    durations: list[float] = []
    with TestClient(app) as client:
        for path in ("/health", "/login", "/static/css/global.css"):
            for _ in range(10):
                started = time.perf_counter()
                response = client.get(path)
                durations.append((time.perf_counter() - started) * 1_000)
                assert response.status_code == 200
    assert percentile(durations, 0.95) < 250
