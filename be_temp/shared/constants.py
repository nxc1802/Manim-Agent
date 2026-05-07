from enum import StrEnum


class SeverityLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


class ReviewLoopMode(StrEnum):
    AUTO = "auto"
    HITL = "hitl"


class MaxRoundsExceededAction(StrEnum):
    HITL_OR_FAIL = "hitl_or_fail"
    FAIL = "failed"
