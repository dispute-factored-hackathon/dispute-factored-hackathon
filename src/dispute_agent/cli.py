"""Interactive command-line demonstration of mock name identification."""

from __future__ import annotations

import argparse
import os

from .authentication import AuthenticationAgent, AuthStatus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the mock call-center identification flow.")
    parser.add_argument(
        "--customers",
        default=os.getenv("CUSTOMERS_CSV", "data/raw/customers.csv"),
        help="Path to customers.csv (or set CUSTOMERS_CSV).",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    agent = AuthenticationAgent(args.customers)
    print("DEMO ONLY: full-name lookup is not secure banking authentication.")
    result = agent.start()
    while result.status in {AuthStatus.NEEDS_NAME, AuthStatus.NOT_FOUND}:
        answer = input(f"Agent: {result.message}\nCustomer: ")
        result = agent.handle_answer(answer)
    print(f"Agent: {result.message}")
    print(f"Status: {result.status.value}")
    if result.customer:
        print(f"Customer ID: {result.customer.customer_id}")
        print(f"Assurance: {result.assurance_level}")
    return 0 if result.authenticated else 1


if __name__ == "__main__":
    raise SystemExit(main())
