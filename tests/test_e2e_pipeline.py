"""
End-to-End Pipeline Integration Tests — Phase 9.

Exercises the real AIFI production pipeline against realistic execution trace fixtures:
- Trace loading & validation
- Failure detection (P9-T02)
- Deterministic diagnosis (P9-T02)
- Reproduction flow (P9-T03)
- Verification flow (P9-T04)
"""

import json
from pathlib import Path
import pytest

import aifi
from aifi import (
    Trace,
    validate_trace,
    detect_failures,
    diagnose_failures,
    reproduce_failure,
    reproduce_trace,
    verify_fix,
    VerificationRequest,
    VerificationStatus,
    ReproductionStatus,
    FailureType,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(filename: str) -> Trace:
    path = FIXTURES_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    trace = aifi.trace_from_dict(data)
    validate_trace(trace)
    return trace


def test_p9_t02_analysis_flow_tool_execution_failure():
    trace = _load_fixture("tool_execution_failure.json")
    detection = detect_failures(trace)
    assert detection.has_failures is True
    assert len(detection.findings) == 1
    finding = detection.findings[0]
    assert finding.failure_type == FailureType.TOOL_EXECUTION_FAILURE.value
    assert finding.evidence["call_id"] == "call_calc_001"

    diagnosis = diagnose_failures(trace, detection)
    assert len(diagnosis.diagnoses) == 1
    diag = diagnosis.diagnoses[0]
    assert "ZeroDivisionError" in diag.likely_cause
    assert "python_calculator" in diag.evidence[0]


def test_p9_t02_analysis_flow_repeated_action_loop():
    trace = _load_fixture("repeated_action_loop.json")
    detection = detect_failures(trace)
    assert detection.has_failures is True
    finding = detection.findings[0]
    assert finding.failure_type == FailureType.REPEATED_ACTION_LOOP.value
    assert finding.evidence["repeat_count"] == 3

    diagnosis = diagnose_failures(trace, detection)
    assert len(diagnosis.diagnoses) == 1
    assert "search_dir" in diagnosis.diagnoses[0].likely_cause


def test_p9_t02_analysis_flow_execution_error_event():
    trace = _load_fixture("execution_error_event.json")
    detection = detect_failures(trace)
    assert detection.has_failures is True
    finding = detection.findings[0]
    assert finding.failure_type == FailureType.EXECUTION_ERROR_EVENT.value
    assert finding.evidence["error_type"] == "ConnectionTimeoutError"

    diagnosis = diagnose_failures(trace, detection)
    assert len(diagnosis.diagnoses) == 1
    diag = diagnosis.diagnoses[0]
    assert "ConnectionTimeoutError" in diag.evidence[1]
    assert "HTTP request to https://api.reports.internal" in diag.likely_cause


def test_p9_t02_analysis_flow_invalid_tool_selection():
    trace = _load_fixture("invalid_tool_selection.json")
    detection = detect_failures(trace)
    assert detection.has_failures is True
    # Has tool execution failure as well (result was error)
    invalid_findings = [f for f in detection.findings if f.failure_type == FailureType.INVALID_TOOL_SELECTION.value]
    assert len(invalid_findings) == 1
    assert invalid_findings[0].evidence["tool_name"] == "deprecated_db_query"

    diagnosis = diagnose_failures(trace, detection)
    invalid_diags = [d for d in diagnosis.diagnoses if d.failure_type == FailureType.INVALID_TOOL_SELECTION.value]
    assert len(invalid_diags) == 1
    assert "deprecated_db_query" in invalid_diags[0].likely_cause


def test_p9_t02_analysis_flow_unresolved_tool_call():
    trace = _load_fixture("unresolved_tool_call.json")
    detection = detect_failures(trace)
    assert detection.has_failures is True
    finding = detection.findings[0]
    assert finding.failure_type == FailureType.UNRESOLVED_TOOL_CALL.value
    assert finding.evidence["call_id"] == "call_async_99"

    diagnosis = diagnose_failures(trace, detection)
    assert len(diagnosis.diagnoses) == 1
    assert "call_async_99" in diagnosis.diagnoses[0].likely_cause


def test_p9_t02_analysis_flow_clean_success():
    trace = _load_fixture("clean_success.json")
    detection = detect_failures(trace)
    assert detection.has_failures is False
    assert len(detection.findings) == 0

    diagnosis = diagnose_failures(trace, detection)
    assert len(diagnosis.diagnoses) == 0


def test_p9_t03_reproduction_flow_supported():
    trace = _load_fixture("tool_execution_failure.json")
    detection = detect_failures(trace)
    finding = detection.findings[0]

    def calc_runner(tool_input):
        # Simulate ZeroDivisionError
        expr = tool_input["expression"]
        if "/ 0" in expr:
            raise ZeroDivisionError("division by zero")
        return eval(expr)

    repro_res = reproduce_failure(trace, finding, tool_runners={"python_calculator": calc_runner})
    assert repro_res.status == ReproductionStatus.REPRODUCED.value
    assert "ZeroDivisionError" in repro_res.evidence.get("reproduced_exception", "")


def test_p9_t03_reproduction_flow_unsupported():
    trace = _load_fixture("repeated_action_loop.json")
    repro_results = reproduce_trace(trace)
    assert len(repro_results) == 1
    assert repro_results[0].status == ReproductionStatus.UNABLE_TO_REPRODUCE.value
    assert "outside local AIFI core scope" in repro_results[0].reason


def test_p9_t04_verification_flow_successful_fix():
    pre_trace = _load_fixture("tool_execution_failure.json")
    post_trace = _load_fixture("postfix_success.json")

    detection = detect_failures(pre_trace)
    assert len(detection.findings) == 1
    finding = detection.findings[0]

    verif_req = VerificationRequest(pre_fix_trace=pre_trace, post_fix_trace=post_trace, finding=finding)
    verif_res = verify_fix(verif_req)
    assert verif_res.status == VerificationStatus.FIXED.value
    assert verif_res.evidence["matched_call_id"] == "call_calc_001"
    assert verif_res.evidence["post_fix_status"] == "success"
