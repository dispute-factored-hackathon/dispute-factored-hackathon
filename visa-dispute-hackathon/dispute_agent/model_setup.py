"""Download the intent model before a customer interaction starts."""

from __future__ import annotations

from .intent_classifier import LocalAvoidanceClassifier
from .language_classifier import LocalLanguageClassifier


def main() -> int:
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError:
        print("ML dependencies are missing. Run: uv sync --extra ml")
        return 1

    model_id = LocalAvoidanceClassifier.DEFAULT_MODEL
    print(f"Preparing the local intent model: {model_id}")
    AutoTokenizer.from_pretrained(model_id)
    AutoModelForSequenceClassification.from_pretrained(model_id)
    LocalLanguageClassifier()._get_identifier()
    print("Intent and language models ready. Customer interactions can now run without network access.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
