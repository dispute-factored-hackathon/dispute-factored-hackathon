"""Evaluate country-code opening inference with synthetic calling-code cases."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from statistics import mean

from dotenv import load_dotenv

from .openai_interpreter import OpenAITurnInterpreter

CASES = Path(__file__).resolve().parents[1] / "evals" / "openings.jsonl"


def calculate_opening_metrics(rows):
    total = len(rows)
    latencies = sorted(result["latency_ms"] for result, _ in rows)
    p95 = max(0, math.ceil(0.95 * total) - 1)

    def accuracy(predicate):
        return round(sum(predicate(result, case) for result, case in rows) / total, 4)

    def has_language_order(result, case):
        positions = [
            result["welcome_message"].find(language) for language in case["language_order"]
        ]
        return all(position >= 0 for position in positions) and positions == sorted(positions)

    return {
        "examples": total,
        "country_region_accuracy": accuracy(
            lambda result, case: (
                case["expected_country"].casefold() in result["country_name"].casefold()
            )
        ),
        "language_accuracy": accuracy(
            lambda result, case: result["primary_language"] == case["primary_language"]
        ),
        "locale_accuracy": accuracy(lambda result, case: result["locale"] == case["locale"]),
        "ambiguity_accuracy": accuracy(
            lambda result, case: result["country_is_ambiguous"] == case["ambiguous"]
        ),
        "language_order_accuracy": accuracy(has_language_order),
        "average_latency_ms": round(mean(latencies), 2),
        "p95_latency_ms": round(latencies[p95], 2),
    }


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    cases = [json.loads(line) for line in CASES.read_text().splitlines() if line]
    interpreter = OpenAITurnInterpreter()
    rows = []
    for case in cases:
        started = time.perf_counter()
        opening = interpreter.generate_opening(case["country_code"])
        result = opening.model_dump()
        result["latency_ms"] = (time.perf_counter() - started) * 1000
        rows.append((result, case))
    metrics = calculate_opening_metrics(rows)
    metrics["llm_api_calls"] = interpreter.api_calls
    print(json.dumps(metrics, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
