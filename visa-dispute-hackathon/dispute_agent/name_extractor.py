"""Constrained local-LLM extraction of a caller's stated full name."""

from __future__ import annotations

import os
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Protocol


class NameExtractor(Protocol):
    def extract(self, text: str) -> str | None: ...


class NameExtractionError(RuntimeError):
    """Raised when the local extraction model is unavailable or fails."""


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = value.casefold()
    value = "".join(character if character.isalnum() or character in " '-" else " " for character in value)
    return " ".join(value.split())


class LocalLLMNameExtractor:
    """Extract names with a local FLAN-T5 model and reject non-grounded output."""

    DEFAULT_MODEL = "google/flan-t5-small"
    PROMPT = """Extract only the person's full name from the final input.
Copy the name exactly from the input. Do not explain. If no name is stated, answer NONE.

Input: My full name is Ana Silva
Name: Ana Silva

Input: Meu nome é José María Pérez López
Name: José María Pérez López

Input: Me llamo Lucía González
Name: Lucía González

Input: {text}
Name:"""

    def __init__(
        self,
        *,
        model_id: str | None = None,
        pipeline_instance: Any | None = None,
    ):
        self.model_id = model_id or os.getenv("NAME_EXTRACTION_MODEL_ID", self.DEFAULT_MODEL)
        self._pipeline = pipeline_instance

    def _get_pipeline(self):
        if self._pipeline is None:
            try:
                from transformers import (
                    AutoModelForSeq2SeqLM,
                    AutoTokenizer,
                    logging as transformers_logging,
                    pipeline,
                )
            except ImportError as exc:
                raise NameExtractionError(
                    "Install the local ML dependencies with: uv sync --extra ml"
                ) from exc
            try:
                transformers_logging.set_verbosity_error()
                tokenizer = AutoTokenizer.from_pretrained(self.model_id, local_files_only=True)
                model = AutoModelForSeq2SeqLM.from_pretrained(
                    self.model_id,
                    local_files_only=True,
                )
                self._pipeline = pipeline(
                    "text2text-generation",
                    model=model,
                    tokenizer=tokenizer,
                    device=-1,
                )
            except Exception as exc:
                raise NameExtractionError(
                    f"Could not load local name extraction model {self.model_id}: {exc}"
                ) from exc
        return self._pipeline

    def extract(self, text: str) -> str | None:
        try:
            output = self._get_pipeline()(
                self.PROMPT.format(text=text),
                max_new_tokens=32,
                do_sample=False,
            )
            candidate = output[0]["generated_text"].strip().strip('"')
        except NameExtractionError:
            raise
        except Exception as exc:
            raise NameExtractionError(f"Local name extraction failed: {exc}") from exc

        if not candidate or candidate.casefold() == "none":
            return None

        grounded_candidate = self._ground_in_original_text(candidate, text)
        if grounded_candidate is None:
            return None
        if len(_normalize(grounded_candidate).split()) < 2:
            return None
        return grounded_candidate

    @staticmethod
    def _ground_in_original_text(candidate: str, text: str) -> str | None:
        """Return the original utterance span that safely grounds the model output."""

        normalized_candidate = _normalize(candidate)
        normalized_text = _normalize(text)
        if not normalized_candidate:
            return None
        if normalized_candidate in normalized_text:
            # Normalization preserves word order but not character offsets. Rebuild from
            # original word spans so accents and casing come from the caller, not the LLM.
            target_words = normalized_candidate.split()
            original_words = text.split()
            normalized_words = [_normalize(word) for word in original_words]
            for index in range(len(original_words) - len(target_words) + 1):
                if normalized_words[index : index + len(target_words)] == target_words:
                    return " ".join(original_words[index : index + len(target_words)]).strip(" ,.!?;:\"")

        candidate_words = normalized_candidate.split()
        if len(candidate_words) < 2:
            return None
        original_words = text.split()
        best_span: str | None = None
        best_score = 0.0
        for size in range(max(2, len(candidate_words) - 1), len(candidate_words) + 2):
            for index in range(len(original_words) - size + 1):
                span = " ".join(original_words[index : index + size]).strip(" ,.!?;:\"")
                score = SequenceMatcher(None, normalized_candidate, _normalize(span)).ratio()
                if score > best_score:
                    best_score = score
                    best_span = span
        # This tolerates a small model spelling error while rejecting unrelated names.
        return best_span if best_score >= 0.88 else None
