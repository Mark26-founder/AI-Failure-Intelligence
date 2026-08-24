from typing import Any, Dict, List, Optional, Set, Union

from aifi.trace.schema import Trace, TraceEvent, EventType, CURRENT_SCHEMA_VERSION


class TraceValidationError(Exception):
    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or [message]


def validate_trace(trace: Union[Trace, Dict[str, Any]]) -> bool:
    errors: List[str] = []

    if isinstance(trace, dict):
        # Basic type checking for dict input
        schema_version = trace.get("schema_version")
        run_id = trace.get("run_id")
        events_list = trace.get("events")
        if not schema_version or not isinstance(schema_version, str):
            errors.append("Trace 'schema_version' must be a non-empty string")
        elif schema_version != CURRENT_SCHEMA_VERSION:
            errors.append(f"Unsupported schema_version '{schema_version}'. Expected '{CURRENT_SCHEMA_VERSION}'")

        if not run_id or not isinstance(run_id, str):
            errors.append("Trace 'run_id' must be a non-empty string")

        if events_list is None or not isinstance(events_list, list):
            errors.append("Trace 'events' must be a list")
            raise TraceValidationError(
                f"Trace validation failed with {len(errors)} error(s)", errors=errors
            )

        # Convert dict events to TraceEvent representations for detailed validation
        parsed_events: List[TraceEvent] = []
        for i, raw_evt in enumerate(events_list):
            if not isinstance(raw_evt, dict):
                errors.append(f"Event at index {i} must be an object (dict)")
                continue
            evt_id = raw_evt.get("event_id")
            evt_type = raw_evt.get("event_type")
            data = raw_evt.get("data")
            timestamp = raw_evt.get("timestamp")

            if not evt_id or not isinstance(evt_id, str):
                errors.append(f"Event at index {i} missing non-empty 'event_id'")
            if not evt_type or not isinstance(evt_type, str):
                errors.append(f"Event at index {i} missing non-empty 'event_type'")
            if data is not None and not isinstance(data, dict):
                errors.append(f"Event '{evt_id or i}' data must be a dictionary")

            parsed_events.append(
                TraceEvent(
                    event_id=str(evt_id) if evt_id else "",
                    event_type=str(evt_type) if evt_type else "",
                    data=data if isinstance(data, dict) else {},
                    timestamp=str(timestamp) if timestamp else None,
                )
            )

        events_to_validate = parsed_events

    elif isinstance(trace, Trace):
        if not trace.schema_version or not isinstance(trace.schema_version, str):
            errors.append("Trace 'schema_version' must be a non-empty string")
        elif trace.schema_version != CURRENT_SCHEMA_VERSION:
            errors.append(f"Unsupported schema_version '{trace.schema_version}'. Expected '{CURRENT_SCHEMA_VERSION}'")

        if not trace.run_id or not isinstance(trace.run_id, str):
            errors.append("Trace 'run_id' must be a non-empty string")

        if not isinstance(trace.events, list):
            errors.append("Trace 'events' must be a list")
            raise TraceValidationError(
                f"Trace validation failed with {len(errors)} error(s)", errors=errors
            )

        events_to_validate = trace.events
    else:
        raise TraceValidationError("Invalid trace input type. Expected Trace instance or dict.")

    seen_event_ids: Set[str] = set()
    active_tool_calls: Set[str] = set()

    for i, event in enumerate(events_to_validate):
        if not event.event_id:
            errors.append(f"Event at index {i} has empty event_id")
        elif event.event_id in seen_event_ids:
            errors.append(f"Duplicate event_id '{event.event_id}' at index {i}")
        else:
            seen_event_ids.add(event.event_id)

        if not event.event_type:
            errors.append(f"Event '{event.event_id or i}' has empty event_type")
        elif not EventType.has_value(event.event_type):
            errors.append(
                f"Event '{event.event_id}' has invalid event_type '{event.event_type}'"
            )

        if not isinstance(event.data, dict):
            errors.append(f"Event '{event.event_id}' data must be a dictionary")
            continue

        # Check event type specific fields
        if event.event_type == EventType.TOOL_CALL.value:
            tool_name = event.data.get("tool_name")
            call_id = event.data.get("call_id")
            if not tool_name or not isinstance(tool_name, str):
                errors.append(f"tool_call event '{event.event_id}' missing required string field 'tool_name'")
            if not call_id or not isinstance(call_id, str):
                errors.append(f"tool_call event '{event.event_id}' missing required string field 'call_id'")
            else:
                active_tool_calls.add(call_id)

        elif event.event_type == EventType.TOOL_RESULT.value:
            call_id = event.data.get("call_id")
            if not call_id or not isinstance(call_id, str):
                errors.append(f"tool_result event '{event.event_id}' missing required string field 'call_id'")
            elif call_id not in active_tool_calls:
                errors.append(
                    f"tool_result event '{event.event_id}' references call_id '{call_id}' which has no preceding tool_call"
                )

    if errors:
        raise TraceValidationError(
            f"Trace validation failed with {len(errors)} error(s)", errors=errors
        )

    return True
