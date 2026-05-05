from enum import Enum

class SeverityLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"

class ReviewLoopMode(str, Enum):
    AUTO = "auto"
    HITL = "hitl"

class MaxRoundsExceededAction(str, Enum):
    HITL_OR_FAIL = "hitl_or_fail"
    FAIL = "failed"
