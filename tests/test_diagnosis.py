import pytest

from aifi.detection import detect_failures
from aifi.diagnosis import diagnose_failures
from aifi.trace import Trace, TraceEvent, EventType, TraceValidationError


def test_diagnose_successful_trace():
    event1 = TraceEvent(event_id="e1", event_type=EventType.MODEL_CALL, data={"prompt": "hi"})
    event2 = TraceEvent(event_id="e2", event_type=EventType.FINAL_RESULT, data={"output": "Done"})
    trace = Trace(run_id="run-success", events=[event1, event2])

    result = diagnose_failures(trace)
    assert len(result.diagnoses) == 0


def test_diagnose_tool_execution_failure():
    event1 = TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "python_eval", "call_id": "c1", "tool_input": {"code": "1/0"}})
    event2 = TraceEvent(event_id="e2", event_type=EventType.TOOL_RESULT, data={"call_id": "c1", "status": "error", "error": "ZeroDivisionError"})
    trace = Trace(run_id="run-tool-error", events=[event1, event2])

    result = diagnose_failures(trace)
    assert len(result.diagnoses) == 1
    diag = result.diagnoses[0]
    assert diag.failure_type == "tool_execution_failure"
    assert "ZeroDivisionError" in diag.likely_cause
    assert diag.confidence == 1.0
    assert diag.is_certain is True
    assert any("python_eval" in e for e in diag.evidence)
    assert diag.inference != ""


def test_diagnose_repeated_action_loop():
    events = [
        TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "fetch", "call_id": "c1", "tool_input": {"url": "http://x"}}),
        TraceEvent(event_id="e2", event_type=EventType.TOOL_RESULT, data={"call_id": "c1", "status": "success", "output": "ok"}),
        TraceEvent(event_id="e3", event_type=EventType.TOOL_CALL, data={"tool_name": "fetch", "call_id": "c2", "tool_input": {"url": "http://x"}}),
        TraceEvent(event_id="e4", event_type=EventType.TOOL_RESULT, data={"call_id": "c2", "status": "success", "output": "ok"}),
        TraceEvent(event_id="e5", event_type=EventType.TOOL_CALL, data={"tool_name": "fetch", "call_id": "c3", "tool_input": {"url": "http://x"}}),
        TraceEvent(event_id="e6", event_type=EventType.TOOL_RESULT, data={"call_id": "c3", "status": "success", "output": "ok"}),
    ]
    trace = Trace(run_id="run-loop", events=events)

    result = diagnose_failures(trace)
    assert len(result.diagnoses) == 1
    diag = result.diagnoses[0]
    assert diag.failure_type == "repeated_action_loop"
    assert "fetch" in diag.likely_cause
    assert diag.confidence == 0.9
    assert diag.is_certain is False


def test_diagnose_unresolved_tool_call_truncated_vs_terminated():
    # Case A: Truncated trace (ends immediately)
    trace_truncated = Trace(
        run_id="run-trunc",
        events=[TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "search", "call_id": "c1"})],
    )
    result_a = diagnose_failures(trace_truncated)
    assert len(result_a.diagnoses) == 1
    diag_a = result_a.diagnoses[0]
    assert diag_a.confidence == 0.70
    assert diag_a.is_certain is False
    assert "truncated" in diag_a.likely_cause.lower() or "interrupted" in diag_a.likely_cause.lower()

    # Case B: Execution terminated with final_result
    trace_terminated = Trace(
        run_id="run-term",
        events=[
            TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "search", "call_id": "c1"}),
            TraceEvent(event_id="e2", event_type=EventType.FINAL_RESULT, data={"output": "Finished early"}),
        ],
    )
    result_b = diagnose_failures(trace_terminated)
    assert len(result_b.diagnoses) == 1
    diag_b = result_b.diagnoses[0]
    assert diag_b.confidence == 0.85
    assert "completed" in diag_b.likely_cause.lower() or "errored" in diag_b.likely_cause.lower()


def test_diagnose_multiple_failures():
    events = [
        TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "bad_tool", "call_id": "c1", "is_valid": False}),
        TraceEvent(event_id="e2", event_type=EventType.TOOL_RESULT, data={"call_id": "c1", "status": "error", "error": "Unknown tool"}),
        TraceEvent(event_id="e3", event_type=EventType.ERROR, data={"error_type": "FatalError", "message": "Crash"}),
    ]
    trace = Trace(run_id="run-multi", events=events)

    result = diagnose_failures(trace)
    assert len(result.diagnoses) == 3
    types = {d.failure_type for d in result.diagnoses}
    assert "invalid_tool_selection" in types
    assert "tool_execution_failure" in types
    assert "execution_error_event" in types
