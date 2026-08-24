# AIFI Example: End-to-End Workflow

This example demonstrates using the primary `aifi` Python API to execute a complete failure intelligence pipeline:
1. **Trace Creation & Validation**
2. **Failure Detection**
3. **Deterministic Diagnosis**
4. **Failure Reproduction**
5. **Fix Verification**

```python
from aifi import (
    Trace,
    TraceEvent,
    EventType,
    validate_trace,
    detect_failures,
    diagnose_failures,
    reproduce_trace,
    verify_fix,
    VerificationRequest,
    ReproductionStatus,
    VerificationStatus,
)

# 1. Create a Pre-Fix Trace containing a failing tool call
pre_fix_trace = Trace(
    run_id="run-001-pre-fix",
    events=[
        TraceEvent(
            event_id="evt-1",
            event_type=EventType.MODEL_CALL,
            data={"prompt": "Calculate 10 / 0"}
        ),
        TraceEvent(
            event_id="evt-2",
            event_type=EventType.TOOL_CALL,
            data={"tool_name": "divide", "call_id": "call-1", "tool_input": {"a": 10, "b": 0}}
        ),
        TraceEvent(
            event_id="evt-3",
            event_type=EventType.TOOL_RESULT,
            data={"call_id": "call-1", "status": "error", "error": "ZeroDivisionError"}
        ),
    ]
)

# Validate trace
validate_trace(pre_fix_trace)

# 2. Detect failures
detection_result = detect_failures(pre_fix_trace)
print(f"Has Failures: {detection_result.has_failures}")
print(f"Findings Count: {len(detection_result.findings)}")
failing_finding = detection_result.findings[0]
print(f"Detected Failure: {failing_finding.failure_type}")

# 3. Diagnose failures
diagnosis_result = diagnose_failures(pre_fix_trace, detection_result)
for diag in diagnosis_result.diagnoses:
    print(f"Likely Cause: {diag.likely_cause}")
    print(f"Inference: {diag.inference}")

# 4. Attempt Reproduction locally with a registered tool runner
def divide_runner(tool_input):
    return tool_input["a"] / tool_input["b"]

repro_results = reproduce_trace(pre_fix_trace, tool_runners={"divide": divide_runner})
for repro in repro_results:
    print(f"Reproduction Status: {repro.status}")  # "reproduced"

# 5. Create a Post-Fix Trace (e.g., after fixing input or tool logic)
post_fix_trace = Trace(
    run_id="run-001-post-fix",
    events=[
        TraceEvent(
            event_id="evt-1",
            event_type=EventType.MODEL_CALL,
            data={"prompt": "Calculate 10 / 2"}
        ),
        TraceEvent(
            event_id="evt-2",
            event_type=EventType.TOOL_CALL,
            data={"tool_name": "divide", "call_id": "call-1", "tool_input": {"a": 10, "b": 2}}
        ),
        TraceEvent(
            event_id="evt-3",
            event_type=EventType.TOOL_RESULT,
            data={"call_id": "call-1", "status": "success", "output": 5}
        ),
    ]
)

# 6. Verify Fix
verification_req = VerificationRequest(
    pre_fix_trace=pre_fix_trace,
    post_fix_trace=post_fix_trace,
    finding=failing_finding,
)
verify_res = verify_fix(verification_req)
print(f"Fix Verification Status: {verify_res.status}")  # "fixed"
print(f"Reason: {verify_res.reason}")
```

## Special Status Handling Notes

- **Reproduction (`ReproductionStatus.UNABLE_TO_REPRODUCE`)**: Returned when a failure type (such as model decision loops `repeated_action_loop` or `unresolved_tool_call`) requires active agent runtime orchestration outside local AIFI core scope, or when no runner is registered for a failing tool.
- **Verification (`VerificationStatus.UNABLE_TO_VERIFY`)**: Returned when post-fix evidence is insufficient (e.g. the failing tool was never exercised in the post-fix trace, or a trace is incomplete without a `final_result`).
