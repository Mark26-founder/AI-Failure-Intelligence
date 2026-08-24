import pytest

from aifi.detection import detect_failures, FailureType
from aifi.reproduction import (
    reproduce_failure,
    reproduce_trace,
    ReproductionStatus,
)
from aifi.trace import Trace, TraceEvent, EventType


def test_reproduce_tool_execution_failure_success():
    event1 = TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "divide", "call_id": "c1", "tool_input": {"a": 10, "b": 0}})
    event2 = TraceEvent(event_id="e2", event_type=EventType.TOOL_RESULT, data={"call_id": "c1", "status": "error", "error": "ZeroDivisionError"})
    trace = Trace(run_id="run-repro-1", events=[event1, event2])

    detection = detect_failures(trace)
    assert len(detection.findings) == 1

    def divide_runner(tool_input):
        return 10 / tool_input["b"]  # Will raise ZeroDivisionError

    result = reproduce_failure(trace, detection.findings[0], tool_runners={"divide": divide_runner})
    assert result.status == ReproductionStatus.REPRODUCED.value
    assert "ZeroDivisionError" in result.evidence.get("reproduced_exception", "")


def test_reproduce_tool_execution_failure_not_reproduced():
    event1 = TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "divide", "call_id": "c1", "tool_input": {"a": 10, "b": 2}})
    event2 = TraceEvent(event_id="e2", event_type=EventType.TOOL_RESULT, data={"call_id": "c1", "status": "error", "error": "Flaky error"})
    trace = Trace(run_id="run-repro-2", events=[event1, event2])

    detection = detect_failures(trace)

    def divide_runner(tool_input):
        return {"status": "success", "result": 5}

    result = reproduce_failure(trace, detection.findings[0], tool_runners={"divide": divide_runner})
    assert result.status == ReproductionStatus.NOT_REPRODUCED.value
    assert result.reason == "Tool execution completed successfully without error during reproduction attempt"


def test_reproduce_tool_execution_failure_unable_no_runner():
    event1 = TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "remote_api", "call_id": "c1", "tool_input": {}})
    event2 = TraceEvent(event_id="e2", event_type=EventType.TOOL_RESULT, data={"call_id": "c1", "status": "error", "error": "500 Internal Server Error"})
    trace = Trace(run_id="run-repro-3", events=[event1, event2])

    detection = detect_failures(trace)

    result = reproduce_failure(trace, detection.findings[0], tool_runners={})
    assert result.status == ReproductionStatus.UNABLE_TO_REPRODUCE.value
    assert "No registered local tool runner" in result.reason


def test_reproduce_unresolved_tool_call_unable_to_reproduce():
    event = TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "async_job", "call_id": "c100"})
    trace = Trace(run_id="run-unresolved", events=[event])

    detection = detect_failures(trace)
    assert len(detection.findings) == 1
    assert detection.findings[0].failure_type == FailureType.UNRESOLVED_TOOL_CALL.value

    result = reproduce_failure(trace, detection.findings[0])
    assert result.status == ReproductionStatus.UNABLE_TO_REPRODUCE.value
    assert "outside local AIFI core scope" in result.reason


def test_reproduce_unsupported_model_loop_failure():
    events = [
        TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "fetch", "call_id": "c1", "tool_input": {"url": "http://x"}}),
        TraceEvent(event_id="e2", event_type=EventType.TOOL_RESULT, data={"call_id": "c1", "status": "success"}),
        TraceEvent(event_id="e3", event_type=EventType.TOOL_CALL, data={"tool_name": "fetch", "call_id": "c2", "tool_input": {"url": "http://x"}}),
        TraceEvent(event_id="e4", event_type=EventType.TOOL_RESULT, data={"call_id": "c2", "status": "success"}),
        TraceEvent(event_id="e5", event_type=EventType.TOOL_CALL, data={"tool_name": "fetch", "call_id": "c3", "tool_input": {"url": "http://x"}}),
        TraceEvent(event_id="e6", event_type=EventType.TOOL_RESULT, data={"call_id": "c3", "status": "success"}),
    ]
    trace = Trace(run_id="run-repro-loop", events=events)

    results = reproduce_trace(trace)
    assert len(results) == 1
    assert results[0].status == ReproductionStatus.UNABLE_TO_REPRODUCE.value
    assert "outside local AIFI core scope" in results[0].reason


def test_reproduce_tool_execution_failure_different_exception_type():
    event1 = TraceEvent(event_id="e1", event_type=EventType.TOOL_CALL, data={"tool_name": "divide", "call_id": "c1", "tool_input": {"a": 10, "b": 0}})
    event2 = TraceEvent(event_id="e2", event_type=EventType.TOOL_RESULT, data={"call_id": "c1", "status": "error", "error": "ZeroDivisionError: integer division by zero"})
    trace = Trace(run_id="run-repro-diff-exc", events=[event1, event2])

    detection = detect_failures(trace)
    assert len(detection.findings) == 1

    def divide_runner_wrong_exc(tool_input):
        raise FileNotFoundError("missing_file.txt")

    result = reproduce_failure(trace, detection.findings[0], tool_runners={"divide": divide_runner_wrong_exc})
    assert result.status == ReproductionStatus.NOT_REPRODUCED.value
    assert "FileNotFoundError" in result.reason or "differs from original" in result.reason

