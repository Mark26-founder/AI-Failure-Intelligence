from typing import Any, Dict, List, Optional, Union

from aifi.detection.engine import detect_failures
from aifi.detection.models import DetectionResult, FailureFinding, FailureType
from aifi.diagnosis.models import DiagnosisFinding, DiagnosisResult
from aifi.trace.schema import Trace, EventType
from aifi.trace.serialization import trace_from_dict
from aifi.trace.validator import validate_trace


def diagnose_failures(
    trace: Union[Trace, Dict[str, Any]],
    detection_result: Optional[DetectionResult] = None,
) -> DiagnosisResult:
    # 1. Validate trace
    validate_trace(trace)

    if isinstance(trace, dict):
        trace_obj = trace_from_dict(trace)
    else:
        trace_obj = trace

    # 2. Get detection result if not provided
    if detection_result is None:
        detection_result = detect_failures(trace_obj)

    diagnoses: List[DiagnosisFinding] = []

    for finding in detection_result.findings:
        diagnosis = _diagnose_finding(trace_obj, finding)
        if diagnosis:
            diagnoses.append(diagnosis)

    return DiagnosisResult(run_id=trace_obj.run_id, diagnoses=diagnoses)


def _diagnose_finding(trace: Trace, finding: FailureFinding) -> DiagnosisFinding:
    ftype = finding.failure_type

    if ftype == FailureType.TOOL_EXECUTION_FAILURE.value:
        return _diagnose_tool_execution_failure(trace, finding)
    elif ftype == FailureType.REPEATED_ACTION_LOOP.value:
        return _diagnose_repeated_action_loop(trace, finding)
    elif ftype == FailureType.EXECUTION_ERROR_EVENT.value:
        return _diagnose_execution_error_event(trace, finding)
    elif ftype == FailureType.INVALID_TOOL_SELECTION.value:
        return _diagnose_invalid_tool_selection(trace, finding)
    elif ftype == FailureType.UNRESOLVED_TOOL_CALL.value:
        return _diagnose_unresolved_tool_call(trace, finding)
    else:
        # Generic fallback for custom/unknown failure types
        return DiagnosisFinding(
            failure_type=ftype,
            likely_cause=finding.explanation,
            evidence=[f"Finding evidence: {finding.evidence}"],
            inference="Detected failure based on trace criteria",
            confidence=0.8,
            is_certain=False,
        )


def _diagnose_tool_execution_failure(trace: Trace, finding: FailureFinding) -> DiagnosisFinding:
    call_id = finding.evidence.get("call_id", "")
    error_content = finding.evidence.get("error", "")
    status = finding.evidence.get("status", "")

    # Look up tool_call event for details
    tool_name = "unknown"
    tool_input = {}
    for evt in trace.events:
        if evt.event_type == EventType.TOOL_CALL.value and evt.data.get("call_id") == call_id:
            tool_name = evt.data.get("tool_name", "unknown")
            tool_input = evt.data.get("tool_input", {})
            break

    evidence = [
        f"Tool '{tool_name}' invoked with call_id '{call_id}' and input {tool_input}",
        f"Tool result returned status='{status}' error='{error_content}'",
    ]

    err_str = str(error_content) if error_content else "unspecified error"
    likely_cause = f"Tool '{tool_name}' execution failed with error: {err_str}"
    inference = "Tool returned an error status during execution"
    confidence = 1.0 if error_content else 0.85

    return DiagnosisFinding(
        failure_type=finding.failure_type,
        likely_cause=likely_cause,
        evidence=evidence,
        inference=inference,
        confidence=confidence,
        is_certain=(confidence == 1.0),
    )


def _diagnose_repeated_action_loop(trace: Trace, finding: FailureFinding) -> DiagnosisFinding:
    tool_name = finding.evidence.get("tool_name", "")
    tool_input = finding.evidence.get("tool_input", {})
    repeat_count = finding.evidence.get("repeat_count", 0)
    repeated_event_ids = finding.evidence.get("repeated_event_ids", [])

    evidence = [
        f"Observed {repeat_count} consecutive tool_call events for tool '{tool_name}' with input {tool_input}",
        f"Event IDs in sequence: {repeated_event_ids}",
    ]

    likely_cause = f"Agent entered repeated loop calling tool '{tool_name}' {repeat_count} times with identical arguments"
    inference = "Agent control loop failed to progress or modify parameters based on prior execution state"
    confidence = 0.9  # Probabilistic as internal model motivation is unobserved

    return DiagnosisFinding(
        failure_type=finding.failure_type,
        likely_cause=likely_cause,
        evidence=evidence,
        inference=inference,
        confidence=confidence,
        is_certain=False,
    )


def _diagnose_execution_error_event(trace: Trace, finding: FailureFinding) -> DiagnosisFinding:
    error_type = finding.evidence.get("error_type", "general_error")
    msg = finding.evidence.get("message", "")
    event_id = finding.location.get("event_id", "")

    evidence = [
        f"Execution error event '{event_id}' recorded in trace",
        f"Error type: '{error_type}', message: '{msg}'",
    ]

    likely_cause = f"Workflow halted by execution error: {msg or error_type}"
    inference = "Fatal error event occurred during workflow execution"
    confidence = 1.0 if msg else 0.85

    return DiagnosisFinding(
        failure_type=finding.failure_type,
        likely_cause=likely_cause,
        evidence=evidence,
        inference=inference,
        confidence=confidence,
        is_certain=(confidence == 1.0),
    )


def _diagnose_invalid_tool_selection(trace: Trace, finding: FailureFinding) -> DiagnosisFinding:
    tool_name = finding.evidence.get("tool_name", "")
    call_id = finding.evidence.get("call_id", "")
    event_id = finding.location.get("event_id", "")

    evidence = [
        f"Tool call event '{event_id}' requested tool '{tool_name}' with call_id '{call_id}'",
        "Trace metadata marked tool selection as invalid/unsupported",
    ]

    likely_cause = f"Trace reports tool selection '{tool_name}' as invalid or unsupported"
    inference = "Trace metadata explicitly marks this tool selection as invalid"
    confidence = 1.0

    return DiagnosisFinding(
        failure_type=finding.failure_type,
        likely_cause=likely_cause,
        evidence=evidence,
        inference=inference,
        confidence=confidence,
        is_certain=False,  # Environment tool registry is unobserved by local core; relying on trace annotation
    )



def _diagnose_unresolved_tool_call(trace: Trace, finding: FailureFinding) -> DiagnosisFinding:
    call_id = finding.evidence.get("call_id", "")
    tool_name = finding.evidence.get("tool_name", "")
    event_id = finding.location.get("event_id", "")

    # Check for trailing events in trace
    has_subsequent_terminal = False
    for evt in trace.events:
        if evt.event_id != event_id and evt.event_type in (EventType.FINAL_RESULT.value, EventType.ERROR.value):
            has_subsequent_terminal = True
            break

    if has_subsequent_terminal:
        evidence = [
            f"Tool call '{call_id}' for tool '{tool_name}' at event '{event_id}' has no matching tool_result",
            "Trace contains subsequent termination event (final_result or error)",
        ]
        likely_cause = f"Tool call '{call_id}' for tool '{tool_name}' was dispatched but execution completed/errored before result was received"
        inference = "Agent workflow terminated without waiting for or receiving tool response"
        confidence = 0.85
    else:
        evidence = [
            f"Tool call '{call_id}' for tool '{tool_name}' at event '{event_id}' is unresolved",
            "Trace ends without any subsequent tool_result or termination event",
        ]
        likely_cause = f"Trace was truncated or interrupted immediately after tool call '{call_id}'"
        inference = "Incomplete trace context; impossible to determine if tool execution failed or trace logging was truncated"
        confidence = 0.70  # Explicitly low confidence due to truncated trace evidence limitation

    return DiagnosisFinding(
        failure_type=finding.failure_type,
        likely_cause=likely_cause,
        evidence=evidence,
        inference=inference,
        confidence=confidence,
        is_certain=False,
    )
