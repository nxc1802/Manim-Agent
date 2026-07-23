from __future__ import annotations


class InactiveStepError(RuntimeError):
    """Raised when Backend no longer accepts work for the current AI step."""
