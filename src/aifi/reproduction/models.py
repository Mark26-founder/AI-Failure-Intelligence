from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from aifi.detection.models import FailureFinding


class ReproductionStatus(str, Enum):
    REPRODUCED = "reproduced"
    NOT_REPRODUCED = "not_reproduced"
    UNABLE_TO_REPRODUCE = "unable_to_reproduce"


@dataclass
class ReproductionResult:
    failure_type: str
    status: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    reason: Optional[str] = None
    reproduced_finding: Optional[FailureFinding] = None
