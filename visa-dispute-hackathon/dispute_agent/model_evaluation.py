"""Model benchmark with local metrics and optional LangSmith experiments."""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path
from statistics import mean
from typing import Any

from dotenv import load_dotenv

from .authentication import normalize_name
from .openai_interpreter import OpenAITurnInterpreter

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "evals" / "turns.jsonl"


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def predict(interpreter: OpenAITurnInterpreter, inputs: dict[str, Any]) -> dict[str, Any]:
    interpreter.set_context(phase=inputs["phase"], locale=inputs["locale"])
    started = time.perf_counter()
    analysis = interpreter.analyze(inputs["text"])
    return {
        **analysis.model_dump(mode="json"),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _names_match(prediction: dict[str, Any], reference: dict[str, Any]) -> bool:
    return normalize_name(prediction.get("extracted_name") or "") == normalize_name(
        reference.get("extracted_name") or ""
    )


def _example_is_correct(prediction: dict[str, Any], reference: dict[str, Any]) -> bool:
    return (
        prediction["intent"] == reference["intent"]
        and prediction["language"] == reference["language"]
        and _names_match(prediction, reference)
        and prediction["abuse"] == reference["abuse"]
        and bool(prediction.get("direct_answer")) == reference["expects_answer"]
    )


def calculate_metrics(rows: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    total = len(rows)
    exact = {
        key: sum(pred[key] == ref[key] for pred, ref in rows)
        for key in ("intent", "language", "abuse")
    }
    name_correct = sum(_names_match(pred, ref) for pred, ref in rows)
    answer_correct = sum(
        bool(pred.get("direct_answer")) == ref["expects_answer"] for pred, ref in rows
    )
    abuse_tp = sum(pred["abuse"] == ref["abuse"] == "prompt_abuse" for pred, ref in rows)
    abuse_fp = sum(
        pred["abuse"] == "prompt_abuse" and ref["abuse"] != "prompt_abuse" for pred, ref in rows
    )
    abuse_fn = sum(
        pred["abuse"] != "prompt_abuse" and ref["abuse"] == "prompt_abuse" for pred, ref in rows
    )
    abuse_precision = _safe_divide(abuse_tp, abuse_tp + abuse_fp)
    abuse_recall = _safe_divide(abuse_tp, abuse_tp + abuse_fn)
    latencies = sorted(float(pred["latency_ms"]) for pred, _ in rows)
    p95_index = max(0, math.ceil(0.95 * len(latencies)) - 1)
    all_fields_correct = sum(_example_is_correct(pred, ref) for pred, ref in rows)
    return {
        "examples": total,
        "intent_accuracy": round(_safe_divide(exact["intent"], total), 4),
        "language_accuracy": round(_safe_divide(exact["language"], total), 4),
        "name_extraction_accuracy": round(_safe_divide(name_correct, total), 4),
        "answer_presence_accuracy": round(_safe_divide(answer_correct, total), 4),
        "abuse_accuracy": round(_safe_divide(exact["abuse"], total), 4),
        "abuse_precision": round(abuse_precision, 4),
        "abuse_recall": round(abuse_recall, 4),
        "abuse_f1": round(
            _safe_divide(2 * abuse_precision * abuse_recall, abuse_precision + abuse_recall), 4
        ),
        "complete_example_accuracy": round(_safe_divide(all_fields_correct, total), 4),
        "average_latency_ms": round(mean(latencies), 2),
        "p95_latency_ms": round(latencies[p95_index], 2),
    }


def run_local(cases: list[dict[str, Any]]) -> dict[str, Any]:
    interpreter = OpenAITurnInterpreter()
    rows = [(predict(interpreter, case["inputs"]), case["outputs"]) for case in cases]
    metrics = calculate_metrics(rows)
    metrics["llm_api_calls"] = interpreter.api_calls
    metrics["failures"] = [
        {"text": case["inputs"]["text"], "expected": reference, "actual": prediction}
        for case, (prediction, reference) in zip(cases, rows, strict=True)
        if not (
            prediction["intent"] == reference["intent"]
            and prediction["language"] == reference["language"]
            and prediction["abuse"] == reference["abuse"]
        )
    ]
    return metrics


def run_langsmith(cases: list[dict[str, Any]], dataset_name: str) -> None:
    from langsmith import Client, evaluate
    from langsmith.schemas import Example, Run

    client = Client()
    if not client.has_dataset(dataset_name=dataset_name):
        dataset = client.create_dataset(
            dataset_name=dataset_name,
            description="Synthetic multilingual call-center turn classification benchmark.",
        )
        client.create_examples(
            dataset_id=dataset.id,
            inputs=[case["inputs"] for case in cases],
            outputs=[case["outputs"] for case in cases],
        )

    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        return predict(OpenAITurnInterpreter(), inputs)

    def exact_field(field: str):
        def evaluator(run: Run, example: Example) -> dict[str, Any]:
            return {
                "key": f"{field}_accuracy",
                "score": run.outputs[field] == example.outputs[field],
            }

        return evaluator

    def name_accuracy(run: Run, example: Example) -> dict[str, Any]:
        score = normalize_name(run.outputs.get("extracted_name") or "") == normalize_name(
            example.outputs.get("extracted_name") or ""
        )
        return {"key": "name_extraction_accuracy", "score": score}

    def answer_presence(run: Run, example: Example) -> dict[str, Any]:
        score = bool(run.outputs.get("direct_answer")) == example.outputs["expects_answer"]
        return {"key": "answer_presence_accuracy", "score": score}

    evaluate(
        target,
        data=dataset_name,
        evaluators=[
            exact_field("intent"),
            exact_field("language"),
            exact_field("abuse"),
            name_accuracy,
            answer_presence,
        ],
        experiment_prefix="dispute-agent-turn-classifier",
        description="Schema-classification quality for synthetic multilingual call-center turns.",
        metadata={"model": os.getenv("OPENAI_AGENT_MODEL", OpenAITurnInterpreter.DEFAULT_MODEL)},
        max_concurrency=1,
        client=client,
    )


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument(
        "--langsmith", action="store_true", help="Upload an experiment to LangSmith."
    )
    parser.add_argument(
        "--dataset", default="visa-dispute-authentication-turns-v1", help="LangSmith dataset name."
    )
    args = parser.parse_args()
    cases = load_cases(args.cases)
    if args.langsmith:
        run_langsmith(cases, args.dataset)
        return
    print(json.dumps(run_local(cases), indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
