import pytest

from aifi.trace import (
    Trace,
    TraceEvent,
    EventType,
    dump_trace_json,
    load_trace_json,
    trace_to_dict,
    trace_from_dict,
    validate_trace,
    TraceValidationError,
)


def test_valid_trace_creation():
    event1 = TraceEvent(
        event_id="evt-1",
        event_type=EventType.MODEL_CALL,
        data={"prompt": "Hello"},
        timestamp="2026-08-18T12:00:00Z",
    )
    event2 = TraceEvent(
        event_id="evt-2",
        event_type=EventType.TOOL_CALL,
        data={"tool_name": "calculator", "call_id": "c-1", "tool_input": {"expr": "2+2"}},
    )
    event3 = TraceEvent(
        event_id="evt-3",
        event_type=EventType.TOOL_RESULT,
        data={"call_id": "c-1", "output": "4"},
    )
    trace = Trace(run_id="run-123", events=[event1, event2, event3])

    assert trace.run_id == "run-123"
    assert len(trace.events) == 3
    assert validate_trace(trace) is True


def test_trace_serialization_roundtrip():
    event1 = TraceEvent(
        event_id="evt-1",
        event_type=EventType.TOOL_CALL.value,
        data={"tool_name": "search", "call_id": "c-99"},
        timestamp="2026-08-18T12:00:00Z",
    )
    event2 = TraceEvent(
        event_id="evt-2",
        event_type=EventType.TOOL_RESULT.value,
        data={"call_id": "c-99", "result": "found"},
    )
    trace = Trace(
        run_id="run-456",
        events=[event1, event2],
        metadata={"user": "test_user"},
    )

    json_str = dump_trace_json(trace)
    loaded_trace = load_trace_json(json_str)

    assert loaded_trace.run_id == trace.run_id
    assert loaded_trace.schema_version == trace.schema_version
    assert loaded_trace.metadata == trace.metadata
    assert len(loaded_trace.events) == 2
    assert loaded_trace.events[0].event_id == "evt-1"
    assert loaded_trace.events[0].data["tool_name"] == "search"
    assert loaded_trace.events[1].data["call_id"] == "c-99"
    assert validate_trace(loaded_trace) is True


def test_validation_missing_run_id():
    trace = Trace(run_id="", events=[])
    with pytest.raises(TraceValidationError) as exc_info:
        validate_trace(trace)
    assert any("run_id" in err for err in exc_info.value.errors)


def test_validation_unsupported_schema():
    trace = Trace(run_id="run-1", schema_version="99.0", events=[])
    with pytest.raises(TraceValidationError) as exc_info:
        validate_trace(trace)
    assert any("Unsupported schema_version" in err for err in exc_info.value.errors)


def test_validation_invalid_event_type():
    event = TraceEvent(event_id="evt-1", event_type="invalid_type", data={})
    trace = Trace(run_id="run-1", events=[event])
    with pytest.raises(TraceValidationError) as exc_info:
        validate_trace(trace)
    assert any("invalid event_type" in err for err in exc_info.value.errors)


def test_validation_duplicate_event_id():
    event1 = TraceEvent(event_id="evt-1", event_type=EventType.MODEL_CALL, data={})
    event2 = TraceEvent(event_id="evt-1", event_type=EventType.FINAL_RESULT, data={})
    trace = Trace(run_id="run-1", events=[event1, event2])
    with pytest.raises(TraceValidationError) as exc_info:
        validate_trace(trace)
    assert any("Duplicate event_id" in err for err in exc_info.value.errors)


def test_validation_tool_result_without_tool_call():
    event = TraceEvent(
        event_id="evt-1",
        event_type=EventType.TOOL_RESULT,
        data={"call_id": "nonexistent_call"},
    )
    trace = Trace(run_id="run-1", events=[event])
    with pytest.raises(TraceValidationError) as exc_info:
        validate_trace(trace)
    assert any("no preceding tool_call" in err for err in exc_info.value.errors)


def test_validation_missing_tool_name_in_tool_call():
    event = TraceEvent(
        event_id="evt-1",
        event_type=EventType.TOOL_CALL,
        data={"call_id": "c-1"},  # missing tool_name
    )
    trace = Trace(run_id="run-1", events=[event])
    with pytest.raises(TraceValidationError) as exc_info:
        validate_trace(trace)
    assert any("tool_name" in err for err in exc_info.value.errors)


def test_validate_dict_input():
    raw_dict = {
        "schema_version": "1.0",
        "run_id": "run-dict-1",
        "events": [
            {
                "event_id": "e-1",
                "event_type": "final_result",
                "data": {"output": "done"},
            }
        ],
    }
    assert validate_trace(raw_dict) is True


def test_deserialization_events_not_a_list():
    raw_dict = {"run_id": "r1", "events": "invalid"}
    with pytest.raises(TraceValidationError) as exc:
        trace_from_dict(raw_dict)
    assert "events" in str(exc.value)


def test_deserialization_event_not_a_dict():
    raw_dict = {"run_id": "r1", "events": ["not_a_dict"]}
    with pytest.raises(TraceValidationError) as exc:
        trace_from_dict(raw_dict)
    assert "index 0" in str(exc.value)


def test_deserialization_event_data_invalid_type():
    raw_dict = {
        "run_id": "r1",
        "events": [{"event_id": "e1", "event_type": "final_result", "data": "not_a_dict"}]
    }
    with pytest.raises(TraceValidationError) as exc:
        trace_from_dict(raw_dict)
    assert "data" in str(exc.value)


def test_deserialization_metadata_invalid_type():
    raw_dict = {"run_id": "r1", "metadata": "not_a_dict", "events": []}
    with pytest.raises(TraceValidationError) as exc:
        trace_from_dict(raw_dict)
    assert "metadata" in str(exc.value)


def test_deserialization_missing_required_event_fields():
    raw_dict = {
        "run_id": "r1",
        "events": [{"event_id": "", "event_type": "final_result"}]
    }
    with pytest.raises(TraceValidationError) as exc:
        trace_from_dict(raw_dict)
    assert "event_id" in str(exc.value)

