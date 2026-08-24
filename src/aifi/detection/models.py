from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FailureType(str, Enum):
    TOOL_EXECUTION_FAILURE = "tool_execution_failure"
    REPEATED_ACTION_LOOP = "repeated_action_loop"
    EXECUTION_ERROR_EVENT = "execution_error_event"
    INVALID_TOOL_SELECTION = "invalid_tool_selection"
    UNRESOLVED_TOOL_CALL = "unresolved_tool_call"


@dataclass
class FailureFinding:
    failure_type: str
    severity: str
    location: Dict[str, Any]
    evidence: Dict[str, Any]
    explanation: str
    confidence: float = 1.0


@dataclass
class DetectionResult:
    run_id: str
    findings: List[FailureFinding] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return len(self.findings) > 0
