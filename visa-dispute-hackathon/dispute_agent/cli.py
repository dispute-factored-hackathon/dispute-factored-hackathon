"""Interactive command-line demonstration of mock name identification."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from .agent_graph import LangGraphAuthenticationAgent
from .authentication import AuthenticationAgent, AuthStatus
from .country_context import normalize_country_code
from .openai_interpreter import OpenAITurnInterpreter


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
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if not os.getenv("OPENAI_API_KEY", "").strip():
        print(
            "OPENAI_API_KEY is missing. Add it to the project .env file before running the agent."
        )
        return 2
    args = build_parser().parse_args()
    interpreter = OpenAITurnInterpreter()
    policy = AuthenticationAgent(
        args.customers,
        language=args.language,
        country_code=args.country_code,
    )
    agent = LangGraphAuthenticationAgent(policy, interpreter)
    result = agent.start()
    try:
        while result.status in {
            AuthStatus.NEEDS_NAME,
            AuthStatus.NEEDS_CONFIRMATION,
            AuthStatus.NOT_FOUND,
        }:
            answer = input(f"Agent: {result.message}\nCustomer: ")
            result = agent.handle_answer(answer)
    except (KeyboardInterrupt, EOFError):
        print("\nAgent: Atendimento encerrado. Você pode iniciar uma nova ligação quando desejar.")
        return 130
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
