"""Interactive command-line demonstration of mock name identification."""

from __future__ import annotations

import argparse
import os

from .authentication import AuthenticationAgent, AuthStatus
from .intent_classifier import LocalAvoidanceClassifier, LocalConfirmationClassifier
from .language_classifier import LocalLanguageClassifier
from .name_extractor import LocalLLMNameExtractor
from .country_context import normalize_country_code


def country_code_argument(value: str) -> str:
    try:
        return normalize_country_code(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the mock call-center identification flow.")
    parser.add_argument(
        "--customers",
        default=os.getenv("CUSTOMERS_CSV", "data/raw/customers.csv"),
        help="Path to customers.csv (or set CUSTOMERS_CSV).",
    )
    parser.add_argument(
        "--language",
        choices=("auto", "en", "pt", "es"),
        default=os.getenv("CALLER_LANGUAGE", "auto"),
        help="Caller language: auto, en, pt or es (default: auto).",
    )
    parser.add_argument(
        "--country-code",
        type=country_code_argument,
        help="Caller's telephone country code, for example +55, 52 or +1.",
    )
    parser.add_argument("--debug", action="store_true", help="Show internal demo identifiers.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    intent_classifier = LocalAvoidanceClassifier()
    agent = AuthenticationAgent(
        args.customers,
        intent_classifier,
        language=args.language,
        language_classifier=LocalLanguageClassifier(),
        name_extractor=LocalLLMNameExtractor(),
        country_code=args.country_code,
        confirmation_classifier=LocalConfirmationClassifier(intent_classifier),
    )
    result = agent.start()
    while result.status in {
        AuthStatus.NEEDS_NAME,
        AuthStatus.NEEDS_CONFIRMATION,
        AuthStatus.NOT_FOUND,
    }:
        answer = input(f"Agent: {result.message}\nCustomer: ")
        result = agent.handle_answer(answer)
    print(f"Agent: {result.message}")
    if result.handoff_summary:
        print("\n--- MOCK HANDOFF NOTE (not read to the caller) ---")
        for key, value in result.handoff_summary.items():
            display_value = "not collected" if value is None else value
            print(f"{key}: {display_value}")
    if args.debug and result.customer:
        print(f"Internal status: {result.status.value}")
        print(f"Customer ID: {result.customer.customer_id}")
        print(f"Assurance: {result.assurance_level}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
