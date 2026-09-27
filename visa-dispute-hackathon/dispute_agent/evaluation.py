"""Credential-free regression evaluation for the local prototype."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


class EvaluationResult(unittest.TextTestResult):
    """Collect deterministic scenario outcomes while retaining diagnostics."""


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    suite = unittest.defaultTestLoader.discover(str(project_root / "tests"))
    runner = unittest.TextTestRunner(verbosity=1, resultclass=EvaluationResult)
    result = runner.run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    summary = {
        "evaluation": "local_offline_regression",
        "tests": result.testsRun,
        "passed": passed,
        "failed": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "pass_rate": round(passed / result.testsRun, 4) if result.testsRun else 0.0,
        "credentials_required": False,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
