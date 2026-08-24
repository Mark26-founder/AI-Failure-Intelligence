from typing import Any, Callable, Dict, List, Optional, Union

from aifi.detection.engine import detect_failures
from aifi.detection.models import FailureFinding, FailureType
from aifi.reproduction.models import ReproductionResult, ReproductionStatus
from aifi.trace.schema import Trace, EventType
from aifi.trace.serialization import trace_from_dict
from aifi.trace.validator import validate_trace


ToolRunner = Callable[[Dict[str, Any]], Any]


def reproduce_failure(
    trace: Union[Trace, Dict[str, Any]],
    finding: FailureFinding,
    tool_runners: Optional[Dict[str, ToolRunner]] = None,
) -> ReproductionResult:
    validate_trace(trace)
    if isinstance(trace, dict):
        trace_obj = trace_from_dict(trace)
    else:
        trace_obj = trace

    runners = tool_runners or {}
    ftype = finding.failure_type

    if ftype == FailureType.TOOL_EXECUTION_FAILURE.value:
        return _reproduce_tool_execution_failure(trace_obj, finding, runners)
    else:
        return ReproductionResult(
            failure_type=ftype,
            status=ReproductionStatus.UNABLE_TO_REPRODUCE.value,
            reason=f"Reproduction of failure type '{ftype}' requires active agent execution runtime outside local AIFI core scope",
            evidence={"original_finding": finding.evidence},
        )


def reproduce_trace(
    trace: Union[Trace, Dict[str, Any]],
    tool_runners: Optional[Dict[str, ToolRunner]] = None,
) -> List[ReproductionResult]:
    validate_trace(trace)
    if isinstance(trace, dict):
        trace_obj = trace_from_dict(trace)
    else:
        trace_obj = trace

    detection_result = detect_failures(trace_obj)
    results: List[ReproductionResult] = []

    for finding in detection_result.findings:
        res = reproduce_failure(trace_obj, finding, tool_runners)
        results.append(res)

    return results


def _reproduce_tool_execution_failure(
    trace: Trace,
    finding: FailureFinding,
    runners: Dict[str, ToolRunner],
) -> ReproductionResult:
    call_id = finding.evidence.get("call_id", "")
    tool_name = "unknown"
    tool_input: Dict[str, Any] = {}

    for evt in trace.events:
        if evt.event_type == EventType.TOOL_CALL.value and evt.data.get("call_id") == call_id:
            tool_name = evt.data.get("tool_name", "unknown")
            tool_input = evt.data.get("tool_input", {})
            break

    if tool_name not in runners:
        return ReproductionResult(
            failure_type=finding.failure_type,
            status=ReproductionStatus.UNABLE_TO_REPRODUCE.value,
            reason=f"No registered local tool runner for tool '{tool_name}'",
            evidence={"call_id": call_id, "tool_name": tool_name, "tool_input": tool_input},
        )

    runner = runners[tool_name]
    orig_error = finding.evidence.get("error")

    try:
        output = runner(tool_input)
        output_is_error = isinstance(output, dict) and (
            output.get("status") == "error"
            or output.get("is_error") is True
            or bool(output.get("error"))
        )
        if output_is_error:
            repro_err = output.get("error") or output.get("status")
            match = _match_failure_condition(orig_error, repro_error_type="", repro_err=str(repro_err or ""))
            if match is True:
                return ReproductionResult(
                    failure_type=finding.failure_type,
                    status=ReproductionStatus.REPRODUCED.value,
                    evidence={
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                        "reproduction_output": output,
                    },
                )
            elif match is False:
                return ReproductionResult(
                    failure_type=finding.failure_type,
                    status=ReproductionStatus.NOT_REPRODUCED.value,
                    reason=f"Runner produced error '{repro_err}' which differs from original failure condition '{orig_error}'",
                    evidence={
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                        "reproduction_output": output,
                        "original_error": orig_error,
                    },
                )
            else:
                return ReproductionResult(
                    failure_type=finding.failure_type,
                    status=ReproductionStatus.UNABLE_TO_REPRODUCE.value,
                    reason="Original failure evidence is insufficient to establish equivalence with reproduction output",
                    evidence={
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                        "reproduction_output": output,
                        "original_error": orig_error,
                    },
                )
        else:
            return ReproductionResult(
                failure_type=finding.failure_type,
                status=ReproductionStatus.NOT_REPRODUCED.value,
                reason="Tool execution completed successfully without error during reproduction attempt",
                evidence={
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "reproduction_output": output,
                },
            )
    except Exception as exc:
        exc_type = type(exc).__name__
        exc_msg = str(exc)
        match = _match_failure_condition(orig_error, repro_error_type=exc_type, repro_err=exc_msg)
        if match is True:
            return ReproductionResult(
                failure_type=finding.failure_type,
                status=ReproductionStatus.REPRODUCED.value,
                evidence={
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "reproduced_exception": f"{exc_type}: {exc_msg}",
                },
            )
        elif match is False:
            return ReproductionResult(
                failure_type=finding.failure_type,
                status=ReproductionStatus.NOT_REPRODUCED.value,
                reason=f"Runner raised exception '{exc_type}' which differs from original failure condition '{orig_error}'",
                evidence={
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "reproduced_exception": f"{exc_type}: {exc_msg}",
                    "original_error": orig_error,
                },
            )
        else:
            return ReproductionResult(
                failure_type=finding.failure_type,
                status=ReproductionStatus.UNABLE_TO_REPRODUCE.value,
                reason=f"Original failure evidence is insufficient to establish equivalence with raised exception '{exc_type}'",
                evidence={
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "reproduced_exception": f"{exc_type}: {exc_msg}",
                    "original_error": orig_error,
                },
            )


def _match_failure_condition(
    orig_error: Any,
    repro_error_type: str = "",
    repro_err: str = "",
) -> Optional[bool]:
    if orig_error is None:
        return None

    if isinstance(orig_error, dict):
        orig_type = str(orig_error.get("error_type") or orig_error.get("error") or "").strip()
        orig_msg = str(orig_error.get("message") or "").strip()
    else:
        orig_str = str(orig_error).strip()
        if not orig_str:
            return None
        orig_type = orig_str.split(":")[0].strip()
        orig_msg = orig_str

    if not orig_type and not orig_msg:
        return None

    if repro_error_type:
        if repro_error_type == orig_type or repro_error_type in orig_type or orig_type in repro_error_type:
            return True
        return False

    if repro_err:
        repro_err_type = repro_err.split(":")[0].strip()
        if (
            orig_type
            and (repro_err_type == orig_type or repro_err_type in orig_type or orig_type in repro_err_type)
        ):
            return True
        if orig_msg and (orig_msg in repro_err or repro_err in orig_msg):
            return True
        return False

    return None

