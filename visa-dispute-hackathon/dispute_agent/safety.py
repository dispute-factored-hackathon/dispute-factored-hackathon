"""Cross-cutting safety wrappers for customer-message entry points."""

from __future__ import annotations

from functools import wraps
from typing import Callable, ParamSpec, TypeVar


P = ParamSpec("P")
R = TypeVar("R")


def screen_prompt_abuse(
    method: Callable[..., R],
) -> Callable[..., R]:
    """Mark the public customer ingress whose graph enforces abuse screening.

    The decorator intentionally does not trust or inject a caller-controlled
    "screened" flag. The first eligible graph node performs the authoritative check,
    so both this facade and direct compiled-graph invocations are protected exactly
    once.
    """

    @wraps(method)
    def wrapped(
        instance,
        answer: str | None,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        return method(instance, answer, *args, **kwargs)

    return wrapped
