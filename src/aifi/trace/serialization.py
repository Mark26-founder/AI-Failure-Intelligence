import json
from typing import Any, Dict, Optional

from aifi.trace.schema import Trace, TraceEvent, CURRENT_SCHEMA_VERSION
from aifi.trace.validator import TraceValidationError


def trace_to_dict(trace: Trace) -> Dict[str, Any]:
    return {
        "schema_version": trace.schema_version,
        "run_id": trace.run_id,
        "metadata": trace.metadata,
        "events": [
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "data": event.data,
                "timestamp": event.timestamp,
            }
            for event in trace.events
        ],
    }


def trace_from_dict(data: Dict[str, Any]) -> Trace:
    if not isinstance(data, dict):
        raise TraceValidationError("Trace payload must be a JSON object (dict)")

    schema_version = data.get("schema_version", CURRENT_SCHEMA_VERSION)
    run_id = data.get("run_id", "")

    metadata = data.get("metadata", {})
    if metadata is not None and not isinstance(metadata, dict):
        raise TraceValidationError("Trace 'metadata' must be a dictionary")

    raw_events = data.get("events")
    if raw_events is None or not isinstance(raw_events, list):
        raise TraceValidationError("Trace 'events' must be a list")

    events = []
    for index, raw_event in enumerate(raw_events):
        if not isinstance(raw_event, dict):
            raise TraceValidationError(f"Event at index {index} must be an object (dict)")

        evt_id = raw_event.get("event_id")
        if not evt_id or not isinstance(evt_id, str):
            raise TraceValidationError(f"Event at index {index} missing non-empty string 'event_id'")

        evt_type = raw_event.get("event_type")
        if not evt_type or not isinstance(evt_type, str):
            raise TraceValidationError(f"Event at index {index} missing non-empty string 'event_type'")

        evt_data = raw_event.get("data")
        if evt_data is not None and not isinstance(evt_data, dict):
            raise TraceValidationError(f"Event '{evt_id}' data must be a dictionary")

        event = TraceEvent(
            event_id=evt_id,
            event_type=evt_type,
            data=evt_data if isinstance(evt_data, dict) else {},
            timestamp=raw_event.get("timestamp"),
        )
        events.append(event)

    return Trace(
        schema_version=str(schema_version),
        run_id=str(run_id),
        events=events,
        metadata=metadata or {},
    )



def dump_trace_json(trace: Trace, indent: Optional[int] = 2) -> str:
    return json.dumps(trace_to_dict(trace), indent=indent)


def load_trace_json(json_str: str) -> Trace:
    data = json.loads(json_str)
    return trace_from_dict(data)
