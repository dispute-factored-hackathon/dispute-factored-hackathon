"""Cross-cutting safety wrappers for customer-message entry points."""

from __future__ import annotations

from functools import wraps
from typing import Callable, ParamSpec, Protocol, TypeVar


class SupportsPromptAbuseCheck(Protocol):
    def _check_prompt_abuse(self, answer: str | None): ...


P = ParamSpec("P")
R = TypeVar("R")


def screen_prompt_abuse(
    method: Callable[[SupportsPromptAbuseCheck, str | None, P], R],
) -> Callable[[SupportsPromptAbuseCheck, str | None, P], R]:
    """Run the configured abuse model before every customer-message turn.

    Empty and oversized input remains the conversation policy's responsibility; all
    other messages are screened before graph execution or hosted-model access.
    """

    @wraps(method)
    def wrapped(
        instance: SupportsPromptAbuseCheck,
        answer: str | None,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        safety_result = instance._check_prompt_abuse(answer)
        if safety_result is not None:
            return safety_result
        return method(instance, answer, *args, **kwargs)

    return wrapped
