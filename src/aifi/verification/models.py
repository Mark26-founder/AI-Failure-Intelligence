from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Union

from aifi.detection.models import FailureFinding
from aifi.trace.schema import Trace


class VerificationStatus(str, Enum):
    FIXED = "fixed"
    NOT_FIXED = "not_fixed"
    UNABLE_TO_VERIFY = "unable_to_verify"


@dataclass
class VerificationRequest:
    """
    Pairs a pre-fix trace and a post-fix trace with the specific finding
    that should be verified.

    Both traces must be valid AIFI traces. The finding must have originated
    from the pre_fix_trace.
    """

    pre_fix_trace: Trace
    post_fix_trace: Trace
    finding: FailureFinding


@dataclass
class VerificationResult:
    """
    The outcome of comparing a pre-fix execution to a post-fix execution
    for a specific failure finding.

    status   — one of: fixed, not_fixed, unable_to_verify
    reason   — human-readable explanation of the determination
    evidence — structured facts observed from the post-fix trace that
               support the determination; never derived from text comparison
               or raw event counts alone
    """

    failure_type: str
    status: str
    reason: str
    evidence: Dict[str, Any] = field(default_factory=dict)
