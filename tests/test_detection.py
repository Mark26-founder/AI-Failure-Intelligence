import pytest

from aifi.detection import (
    detect_failures,
    FailureType,
    ToolExecutionFailureDetector,
    RepeatedActionLoopDetector,
    ExecutionErrorDetector,
    InvalidToolSelectionDetector,
    UnresolvedToolCallDetector,
)
from aifi.trace import Trace, TraceEvent, EventType, TraceValidationError


def test_successful_trace_no_failures():
    event1 = TraceEvent(event_id="e1", event_type=EventType.MODEL_CALL, data={"prompt": "hi"})
    event2 = TraceEvent(event_id="e2", event_type=EventType.TOOL_CALL, data={"tool_name": "calc", "call_id": "c1"})
    event3 = TraceEvent(event_id="e3", event_type=EventType.TOOL_RESULT, data={"call_id": "c1", "status": "success", "output": "42"})
    event4 = TraceEvent(event_id="e4", event_type=EventType.FINAL_RESULT, data={"output": "Done"})
    trace = Trace(run_id="run-success", events=[event1, event2, event3, event4])

    result = detect_failures(trace)
    assert result.has_failures is False
    assert len(result.findings) == 0


def test_tool_execution_failure_detector():
    event1 = TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "bash", "call_id": "c1"})
    event2 = TraceEvent(event_id="e2", event_type=EventType.TOOL_RESULT, data={"call_id": "c1", "status": "error", "error": "Command failed"})
    trace = Trace(run_id="run-tool-fail", events=[event1, event2])

    detector = ToolExecutionFailureDetector()
    findings = detector.detect(trace)
    assert len(findings) == 1
    assert findings[0].failure_type == FailureType.TOOL_EXECUTION_FAILURE.value
    assert findings[0].evidence["call_id"] == "c1"


def test_repeated_action_loop_detector():
    events = [
        TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "read_file", "call_id": "c1", "tool_input": {"path": "a.txt"}}),
        TraceEvent(event_id="e2", event_type=EventType.TOOL_RESULT, data={"call_id": "c1", "output": "content"}),
        TraceEvent(event_id="e3", event_type=EventType.TOOL_CALL, data={"tool_name": "read_file", "call_id": "c2", "tool_input": {"path": "a.txt"}}),
        TraceEvent(event_id="e4", event_type=EventType.TOOL_RESULT, data={"call_id": "c2", "output": "content"}),
        TraceEvent(event_id="e5", event_type=EventType.TOOL_CALL, data={"tool_name": "read_file", "call_id": "c3", "tool_input": {"path": "a.txt"}}),
        TraceEvent(event_id="e6", event_type=EventType.TOOL_RESULT, data={"call_id": "c3", "output": "content"}),
    ]
    trace = Trace(run_id="run-loop", events=events)

    detector = RepeatedActionLoopDetector(min_repeats=3)
    findings = detector.detect(trace)
    assert len(findings) == 1
    assert findings[0].failure_type == FailureType.REPEATED_ACTION_LOOP.value
    assert findings[0].evidence["repeat_count"] == 3


def test_repeated_action_loop_negative_case():
    events = [
        TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "read_file", "call_id": "c1", "tool_input": {"path": "a.txt"}}),
        TraceEvent(event_id="e2", event_type=EventType.TOOL_CALL, data={"tool_name": "read_file", "call_id": "c2", "tool_input": {"path": "b.txt"}}),
    ]
    trace = Trace(run_id="run-no-loop", events=events)

    detector = RepeatedActionLoopDetector(min_repeats=3)
    findings = detector.detect(trace)
    assert len(findings) == 0


def test_execution_error_event_detector():
    event = TraceEvent(event_id="e1", event_type=EventType.ERROR, data={"error_type": "TimeoutError", "message": "API timeout"})
    trace = Trace(run_id="run-err", events=[event])

    detector = ExecutionErrorDetector()
    findings = detector.detect(trace)
    assert len(findings) == 1
    assert findings[0].failure_type == FailureType.EXECUTION_ERROR_EVENT.value
    assert findings[0].evidence["error_type"] == "TimeoutError"


def test_invalid_tool_selection_detector():
    event = TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "unknown_tool", "call_id": "c1", "is_valid": False})
    trace = Trace(run_id="run-invalid-tool", events=[event])

    detector = InvalidToolSelectionDetector()
    findings = detector.detect(trace)
    assert len(findings) == 1
    assert findings[0].failure_type == FailureType.INVALID_TOOL_SELECTION.value


def test_unresolved_tool_call_detector():
    event = TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "bash", "call_id": "c100"})
    trace = Trace(run_id="run-unresolved", events=[event])

    detector = UnresolvedToolCallDetector()
    findings = detector.detect(trace)
    assert len(findings) == 1
    assert findings[0].failure_type == FailureType.UNRESOLVED_TOOL_CALL.value
    assert findings[0].evidence["call_id"] == "c100"
    assert findings[0].evidence["truncated"] is True
    assert findings[0].confidence == 0.70


def test_unresolved_tool_call_confirmed_subsequent_events():
    events = [
        TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "bash", "call_id": "c100"}),
        TraceEvent(event_id="e2", event_type=EventType.MODEL_CALL, data={"prompt": "Next step without waiting for result"}),
        TraceEvent(event_id="e3", event_type=EventType.FINAL_RESULT, data={"output": "Finished"}),
    ]
    trace = Trace(run_id="run-unresolved-confirmed", events=events)

    detector = UnresolvedToolCallDetector()
    findings = detector.detect(trace)
    assert len(findings) == 1
    assert findings[0].failure_type == FailureType.UNRESOLVED_TOOL_CALL.value
    assert findings[0].evidence["truncated"] is False
    assert findings[0].confidence == 1.0


def test_combined_detection_multiple_failures():
    events = [
        TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "bash", "call_id": "c1"}),
        TraceEvent(event_id="e2", event_type=EventType.TOOL_RESULT, data={"call_id": "c1", "status": "error", "error": "Disk full"}),
        TraceEvent(event_id="e3", event_type=EventType.ERROR, data={"message": "System crashed"}),
    ]
    trace = Trace(run_id="run-multi-fail", events=events)

    result = detect_failures(trace)
    assert result.has_failures is True
    assert len(result.findings) == 2
    types = {f.failure_type for f in result.findings}
    assert FailureType.TOOL_EXECUTION_FAILURE.value in types
    assert FailureType.EXECUTION_ERROR_EVENT.value in types


def test_detect_failures_invalid_trace_raises():
    invalid_trace = Trace(run_id="", events=[])
    with pytest.raises(TraceValidationError):
        detect_failures(invalid_trace)

