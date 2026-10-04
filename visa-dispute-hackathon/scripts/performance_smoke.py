"""Small dependency-free latency smoke test for the deployed Factored Bank shell."""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.request


def percentile(values: list[float], percentage: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * percentage) - 1)
    return ordered[index]


def measure(url: str, runs: int, timeout: float) -> dict[str, float | int | str]:
    durations: list[float] = []
    status = 0
    for _ in range(runs):
        started = time.perf_counter()
        with urllib.request.urlopen(url, timeout=timeout) as response:
            status = response.status
            response.read()
        durations.append((time.perf_counter() - started) * 1_000)
    return {
        "url": url,
        "runs": runs,
        "status": status,
        "p50_ms": round(percentile(durations, 0.50), 1),
        "p95_ms": round(percentile(durations, 0.95), 1),
        "max_ms": round(max(durations), 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=30)
    parser.add_argument("--max-p95-ms", type=float, default=1_000)
    args = parser.parse_args()
    if args.runs < 2:
        parser.error("--runs must be at least 2")

    base_url = args.base_url.rstrip("/")
    results = []
    try:
        for path in ("/health", "/login", "/static/css/global.css"):
            results.append(measure(f"{base_url}{path}", args.runs, args.timeout_seconds))
    except (TimeoutError, urllib.error.URLError) as error:
        print(json.dumps({"error": type(error).__name__}))
        return 2
    print(json.dumps(results, indent=2))
    return int(any(float(result["p95_ms"]) > args.max_p95_ms for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
