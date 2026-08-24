# AI Failure Intelligence (AIFI)

An open-source, agent-agnostic AI failure debugging system.

AIFI provides a standardized framework for inspecting, diagnosing, reproducing, and verifying fixes for AI agent execution failures.

---

## Problem AIFI Solves

AI agents are complex, non-deterministic systems that fail in subtle ways:
- **Tool Execution Failures**: External tools returning errors or throwing exceptions during execution.
- **Repeated Action Loops**: Agents stuck calling the same tool with identical inputs repeatedly.
- **Execution Error Events**: Unexpected unhandled errors or fatal exceptions in the agent loop.
- **Invalid Tool Selection**: Agents attempting to invoke unsupported or ill-formed tools.
- **Unresolved Tool Calls**: Tool calls dispatched without receiving a corresponding result before termination or logging truncation.

AIFI normalizes agent execution logs into a unified, versioned trace format and provides deterministic failure detection, cause diagnosis, local reproduction, and cross-run fix verification.

---

## Core Workflow

```text
External AI Agent / Trace
         ↓
Trace Validation (validate_trace)
         ↓
Failure Detection (detect_failures)
         ↓
Failure Diagnosis (diagnose_failures)
         ↓
Failure Reproduction (reproduce_failure / reproduce_trace)
         ↓
Fix Verification (verify_fix)
```

1. **Validate**: Ensures execution traces strictly conform to the AIFI schema.
2. **Detect**: Identifies exact failure locations, types, and supporting evidence.
3. **Diagnose**: Evaluates likely root causes, inferring system state and assigning confidence.
4. **Reproduce**: Re-executes failing tool operations locally using registered tool runners to verify failure conditions.
5. **Verify**: Compares pre-fix and post-fix execution traces to determine whether a failure was genuinely resolved, not fixed, or unable to be verified due to insufficient/unattributed evidence.

---

## Trace Format

AIFI operates on normalized execution traces (`schema_version = "1.0"`):

```json
{
  "schema_version": "1.0",
  "run_id": "run-example-101",
  "metadata": {"agent": "my_agent", "environment": "staging"},
  "events": [
    {
      "event_id": "e1",
      "event_type": "model_call",
      "data": {"prompt": "Calculate 10 / 0"},
      "timestamp": "2026-08-23T10:00:00Z"
    },
    {
      "event_id": "e2",
      "event_type": "tool_call",
      "data": {
        "tool_name": "calculator",
        "call_id": "c1",
        "tool_input": {"expression": "10 / 0"}
      },
      "timestamp": "2026-08-23T10:00:01Z"
    },
    {
      "event_id": "e3",
      "event_type": "tool_result",
      "data": {
        "call_id": "c1",
        "status": "error",
        "error": "ZeroDivisionError: division by zero"
      },
      "timestamp": "2026-08-23T10:00:02Z"
    }
  ]
}
```

Supported Event Types:
- `model_call`: LLM prompt/request
- `tool_call`: Tool invocation request
- `tool_result`: Tool execution response/error
- `state_change`: Internal agent state update
- `error`: Execution error event
- `final_result`: Agent workflow termination output

---

## Installation

Install locally via `pip`:

```bash
# Clean editable installation
pip install -e .

# Or standard installation
pip install .
```

Requires Python `>= 3.10`.

---

## Usage

### Python API

```python
import aifi

# 1. Load & Validate Trace
trace_dict = aifi.load_trace_json("path/to/trace.json")
aifi.validate_trace(trace_dict)

# 2. Detect Failures
trace = aifi.trace_from_dict(trace_dict)
detection_result = aifi.detect_failures(trace)
print(f"Has failures: {detection_result.has_failures}")

# 3. Diagnose Failures
diagnosis_result = aifi.diagnose_failures(trace, detection_result)
for diag in diagnosis_result.diagnoses:
    print(f"Type: {diag.failure_type}, Cause: {diag.likely_cause}, Confidence: {diag.confidence}")

# 4. Reproduce Failure
def calc_runner(tool_input):
    # Local Python runner callback for tool reproduction
    expr = tool_input["expression"]
    if "/ 0" in expr:
        raise ZeroDivisionError("division by zero")
    return {"status": "success", "result": eval(expr)}

repro_results = aifi.reproduce_trace(trace, tool_runners={"calculator": calc_runner})
for r in repro_results:
    print(f"Reproduction Status: {r.status}")

# 5. Fix Verification
pre_fix = aifi.trace_from_dict(aifi.load_trace_json("pre_fix.json"))
post_fix = aifi.trace_from_dict(aifi.load_trace_json("post_fix.json"))
finding = detection_result.findings[0]

request = aifi.VerificationRequest(pre_fix_trace=pre_fix, post_fix_trace=post_fix, finding=finding)
verif_result = aifi.verify_fix(request)
print(f"Verification Verdict: {verif_result.status}")
```

### Command Line Interface (CLI)

```bash
# Validate trace file
aifi validate trace.json

# Detect & Diagnose failures
aifi analyze trace.json

# Reproduce failures
aifi reproduce trace.json

# Verify fix between pre-fix and post-fix traces
aifi verify pre_fix.json post_fix.json
```

---

## Adapter Integration

Adapters transform external framework log data into normalized AIFI traces.

```python
from aifi.adapters import GenericAdapter

adapter = GenericAdapter()
raw_log = {
    "run_id": "external-run-001",
    "steps": [
        {"action": "tool_call", "name": "search", "id": "call_1", "input": {"q": "AI"}},
        {"action": "tool_result", "id": "call_1", "output": "results"}
    ]
}

# Convert external data to validated AIFI Trace
trace = adapter.to_trace(raw_log)
```

Custom adapters subclass `BaseAdapter` and implement `convert(external_data) -> Trace`.

---

## License

[MIT License](LICENSE)
