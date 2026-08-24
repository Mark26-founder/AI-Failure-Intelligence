from typing import Any, Dict, List, Optional, Union

from aifi.detection.models import DetectionResult, FailureFinding
from aifi.detection.detectors import (
    BaseDetector,
    ToolExecutionFailureDetector,
    RepeatedActionLoopDetector,
    ExecutionErrorDetector,
    InvalidToolSelectionDetector,
    UnresolvedToolCallDetector,
)
from aifi.trace.schema import Trace
from aifi.trace.serialization import trace_from_dict
from aifi.trace.validator import validate_trace


def get_default_detectors() -> List[BaseDetector]:
    return [
        ToolExecutionFailureDetector(),
        RepeatedActionLoopDetector(),
        ExecutionErrorDetector(),
        InvalidToolSelectionDetector(),
        UnresolvedToolCallDetector(),
    ]


def detect_failures(
    trace: Union[Trace, Dict[str, Any]],
    detectors: Optional[List[BaseDetector]] = None,
) -> DetectionResult:
    # 1. Validate incoming trace
    validate_trace(trace)

    # 2. Ensure Trace object
    if isinstance(trace, dict):
        trace_obj = trace_from_dict(trace)
    else:
        trace_obj = trace

    # 3. Run detectors
    active_detectors = detectors if detectors is not None else get_default_detectors()
    all_findings: List[FailureFinding] = []

    for detector in active_detectors:
        findings = detector.detect(trace_obj)
        all_findings.extend(findings)

    # 4. Deduplicate findings if any duplicate exists
    unique_findings: List[FailureFinding] = []
    seen_keys = set()
    for finding in all_findings:
        loc_key = str(sorted(finding.location.items()))
        key = (finding.failure_type, loc_key)
        if key not in seen_keys:
            seen_keys.add(key)
            unique_findings.append(finding)

    return DetectionResult(run_id=trace_obj.run_id, findings=unique_findings)
