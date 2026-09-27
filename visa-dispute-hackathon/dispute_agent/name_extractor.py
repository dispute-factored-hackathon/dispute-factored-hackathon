"""Legacy policy protocol; runtime name extraction is part of the LLM schema."""

from __future__ import annotations

from typing import Protocol


class NameExtractionError(RuntimeError):
    pass


class NameExtractor(Protocol):
    def extract(self, text: str) -> str | None: ...
