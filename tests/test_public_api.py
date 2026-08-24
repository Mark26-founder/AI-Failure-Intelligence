"""
Tests for Phase 6 — Public Python API.

Verifies that the top-level `aifi` package exports all expected structures
and functions, operates directly on core logic without duplication, and handles
end-to-end workflows and invalid inputs cleanly.
"""

import pytest

import aifi
from aifi import (
    Trace,
    TraceEvent,
    EventType,
    validate_trace,
    detect_failures,
    diagnose_failures,
    reproduce_trace,
    reproduce_failure,
    verify_fix,
    VerificationRequest,
    VerificationStatus,
    ReproductionStatus,
    TraceValidationError,
    FailureType,
)


def test_public_api_exports():
    """Verify that top-level aifi exports expected symbols."""
    expected_symbols = [
        "__version__",
        "Trace",
        "TraceEvent",
        "EventType",
        "validate_trace",
        "load_trace_json",
        "dump_trace_json",
        "trace_to_dict",
        "trace_from_dict",
        "TraceValidationError",
        "detect_failures",
        "DetectionResult",
        "FailureFinding",
        "FailureType",
        "Severity",
        "diagnose_failures",
        "DiagnosisResult",
        "DiagnosisFinding",
        "reproduce_trace",
        "reproduce_failure",
        "ReproductionResult",
        "ReproductionStatus",
        "verify_fix",
        "VerificationRequest",
        "VerificationResult",
        "VerificationStatus",
    ]
    for symbol in expected_symbols:
        assert hasattr(aifi, symbol), f"Top-level package 'aifi' is missing export '{symbol}'"


def test_end_to_end_public_api_workflow():
    """Test full workflow using top-level imports exclusively."""
    # Pre-fix trace with a failing tool call
    pre_events = [
        TraceEvent("e1", EventType.MODEL_CALL, {"prompt": "Divide"}),
        TraceEvent("e2", EventType.TOOL_CALL, {"tool_name": "divide", "call_id": "c1", "tool_input": {"a": 10, "b": 0}}),
        TraceEvent("e3", EventType.TOOL_RESULT, {"call_id": "c1", "status": "error", "error": "ZeroDivisionError"}),
    ]
    pre_trace = Trace(run_id="run-api-pre", events=pre_events)

    # 1. Validation
    validate_trace(pre_trace)

    # 2. Detection
    det_res = detect_failures(pre_trace)
    assert det_res.has_failures is True
    assert len(det_res.findings) == 1
    finding = det_res.findings[0]
    assert finding.failure_type == FailureType.TOOL_EXECUTION_FAILURE.value

    # 3. Diagnosis
    diag_res = diagnose_failures(pre_trace, det_res)
    assert len(diag_res.diagnoses) == 1
    assert "ZeroDivisionError" in diag_res.diagnoses[0].likely_cause

    # 4. Reproduction
    def divide_runner(tool_input):
        return tool_input["a"] / tool_input["b"]

    repro_res = reproduce_failure(pre_trace, finding, tool_runners={"divide": divide_runner})
    assert repro_res.status == ReproductionStatus.REPRODUCED.value

    # 5. Fix Verification
    post_events = [
        TraceEvent("e1", EventType.MODEL_CALL, {"prompt": "Divide"}),
        TraceEvent("e2", EventType.TOOL_CALL, {"tool_name": "divide", "call_id": "c1", "tool_input": {"a": 10, "b": 2}}),
        TraceEvent("e3", EventType.TOOL_RESULT, {"call_id": "c1", "status": "success", "output": 5}),
    ]
    post_trace = Trace(run_id="run-api-post", events=post_events)

    verif_req = VerificationRequest(pre_fix_trace=pre_trace, post_fix_trace=post_trace, finding=finding)
    verif_res = verify_fix(verif_req)
    assert verif_res.status == VerificationStatus.FIXED.value


def test_public_api_invalid_trace_error():
    """Verify that public API validation raises TraceValidationError on bad input."""
    invalid_trace = Trace(run_id="", events=[])
    with pytest.raises(TraceValidationError):
        detect_failures(invalid_trace)
