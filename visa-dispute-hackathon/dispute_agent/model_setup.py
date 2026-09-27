"""Download the intent model before a customer interaction starts."""

from __future__ import annotations

from .intent_classifier import LocalAvoidanceClassifier
from .language_classifier import LocalLanguageClassifier
from .name_extractor import LocalLLMNameExtractor


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
    name_model_id = LocalLLMNameExtractor.DEFAULT_MODEL
    print(f"Preparing the local name extraction LLM: {name_model_id}")
    AutoTokenizer.from_pretrained(name_model_id)
    from transformers import AutoModelForSeq2SeqLM

    AutoModelForSeq2SeqLM.from_pretrained(name_model_id)
    print("Intent, language and name extraction models ready. Customer interactions can now run without network access.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
