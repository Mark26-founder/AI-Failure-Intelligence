from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

CURRENT_SCHEMA_VERSION = "1.0"


class EventType(str, Enum):
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STATE_CHANGE = "state_change"
    ERROR = "error"
    FINAL_RESULT = "final_result"

    @classmethod
    def has_value(cls, value: str) -> bool:
        return value in cls._value2member_map_


@dataclass
class TraceEvent:
    event_id: str
    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[str] = None


@dataclass
class Trace:
    run_id: str
    events: List[TraceEvent] = field(default_factory=list)
    schema_version: str = CURRENT_SCHEMA_VERSION
    metadata: Dict[str, Any] = field(default_factory=dict)
