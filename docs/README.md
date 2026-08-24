[README.md](https://github.com/user-attachments/files/31379693/README.md)
# AIFI Documentation

Welcome to the AI Failure Intelligence (AIFI) documentation.

## Table of Contents
- [Trace Schema Specification](#trace-schema-specification)
- [Failure Types & Detection](#failure-types--detection)
- [Fix Verification Engine](#fix-verification-engine)
- [Adapter Development](#adapter-development)

---

## Trace Schema Specification

AIFI trace version `1.0` requires the following fields:

### Trace Object
- `schema_version` (string, required): Must be `"1.0"`.
- `run_id` (string, required): Non-empty unique execution identifier.
- `metadata` (object, optional): Arbitrary key-value execution context.
- `events` (list of event objects, required): Ordered list of execution events.

### Event Object
- `event_id` (string, required): Unique identifier within the trace.
- `event_type` (string, required): Must be one of `model_call`, `tool_call`, `tool_result`, `state_change`, `error`, `final_result`.
- `data` (object, required): Payload data for the event type.
- `timestamp` (string, optional): ISO-8601 timestamp.

---

## Failure Types & Detection

1. `tool_execution_failure`: `tool_result` event returning error status or exception string.
2. `repeated_action_loop`: 3 or more consecutive identical `tool_call` events (same `tool_name` + `tool_input`).
3. `execution_error_event`: EventType.ERROR recorded in execution trace.
4. `invalid_tool_selection`: `tool_call` event annotated with `is_valid: false` or `error_type: "invalid_tool"`.
5. `unresolved_tool_call`: `tool_call` event without a matching `tool_result` by `call_id`.

---

## Fix Verification Engine

`verify_fix` evaluates pre-fix trace, post-fix trace, and a specific `FailureFinding`.
Verdicts returned:
- `fixed`: Observable evidence confirms original failure condition was resolved in post-fix execution.
- `not_fixed`: Original failure condition persists in post-fix execution.
- `unable_to_verify`: Post-fix trace lacks sufficient or attributed evidence to verify resolution.

---

## Adapter Development

Implement a custom adapter by inheriting from `aifi.adapters.BaseAdapter`:

```python
from typing import Any, Dict
from aifi.adapters import BaseAdapter
from aifi.trace import Trace, TraceEvent, EventType

class MyFrameworkAdapter(BaseAdapter):
    def convert(self, external_data: Dict[str, Any]) -> Trace:
        events = []
        # Map framework log events to TraceEvent objects...
        return Trace(
            schema_version="1.0",
            run_id=external_data.get("id", "run-1"),
            events=events,
        )
```
