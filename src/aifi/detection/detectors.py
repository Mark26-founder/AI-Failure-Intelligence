from abc import ABC, abstractmethod
from typing import Any, Dict, List, Set

from aifi.detection.models import FailureFinding, FailureType, Severity
from aifi.trace.schema import Trace, EventType


class BaseDetector(ABC):
    @abstractmethod
    def detect(self, trace: Trace) -> List[FailureFinding]:
        pass


class ToolExecutionFailureDetector(BaseDetector):
    def detect(self, trace: Trace) -> List[FailureFinding]:
        findings: List[FailureFinding] = []
        for index, event in enumerate(trace.events):
            if event.event_type == EventType.TOOL_RESULT.value:
                data = event.data or {}
                status = data.get("status")
                is_error = data.get("is_error")
                error_content = data.get("error")

                if status == "error" or is_error is True or bool(error_content):
                    call_id = data.get("call_id", "")
                    finding = FailureFinding(
                        failure_type=FailureType.TOOL_EXECUTION_FAILURE.value,
                        severity=Severity.HIGH.value,
                        location={"event_id": event.event_id, "event_index": index},
                        evidence={
                            "call_id": call_id,
                            "status": status,
                            "is_error": is_error,
                            "error": error_content,
                        },
                        explanation=f"Tool execution failed for call_id '{call_id}' at event '{event.event_id}'",
                        confidence=1.0,
                    )
                    findings.append(finding)
        return findings


class RepeatedActionLoopDetector(BaseDetector):
    def __init__(self, min_repeats: int = 3):
        self.min_repeats = min_repeats

    def detect(self, trace: Trace) -> List[FailureFinding]:
        findings: List[FailureFinding] = []
        current_sequence: List[Dict[str, Any]] = []

        for index, event in enumerate(trace.events):
            if event.event_type == EventType.TOOL_CALL.value:
                tool_name = event.data.get("tool_name", "")
                tool_input = event.data.get("tool_input", {})
                call_info = {
                    "event_id": event.event_id,
                    "event_index": index,
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                }

                if not current_sequence:
                    current_sequence.append(call_info)
                else:
                    prev = current_sequence[-1]
                    if (
                        prev["tool_name"] == tool_name
                        and prev["tool_input"] == tool_input
                    ):
                        current_sequence.append(call_info)
                    else:
                        if len(current_sequence) >= self.min_repeats:
                            findings.append(self._create_finding(current_sequence))
                        current_sequence = [call_info]
            # Note: Non-tool_call events between tool calls are preserved without breaking loop count
            # unless a tool_result produces output change, but here we inspect tool_call sequence strictly.

        if len(current_sequence) >= self.min_repeats:
            findings.append(self._create_finding(current_sequence))

        return findings

    def _create_finding(self, sequence: List[Dict[str, Any]]) -> FailureFinding:
        start_event = sequence[0]
        end_event = sequence[-1]
        event_ids = [s["event_id"] for s in sequence]
        return FailureFinding(
            failure_type=FailureType.REPEATED_ACTION_LOOP.value,
            severity=Severity.MEDIUM.value,
            location={
                "start_event_id": start_event["event_id"],
                "end_event_id": end_event["event_id"],
                "repeat_count": len(sequence),
            },
            evidence={
                "tool_name": start_event["tool_name"],
                "tool_input": start_event["tool_input"],
                "repeated_event_ids": event_ids,
                "repeat_count": len(sequence),
            },
            explanation=(
                f"Repeated action loop detected: tool '{start_event['tool_name']}' "
                f"called {len(sequence)} consecutive times with identical input"
            ),
            confidence=1.0,
        )


class ExecutionErrorDetector(BaseDetector):
    def detect(self, trace: Trace) -> List[FailureFinding]:
        findings: List[FailureFinding] = []
        for index, event in enumerate(trace.events):
            if event.event_type == EventType.ERROR.value:
                data = event.data or {}
                error_msg = data.get("message") or data.get("error") or "Execution error occurred"
                error_type = data.get("error_type", "general_error")

                finding = FailureFinding(
                    failure_type=FailureType.EXECUTION_ERROR_EVENT.value,
                    severity=Severity.HIGH.value,
                    location={"event_id": event.event_id, "event_index": index},
                    evidence={"error_type": error_type, "message": error_msg, "raw_data": data},
                    explanation=f"Execution error event '{event.event_id}': {error_msg}",
                    confidence=1.0,
                )
                findings.append(finding)
        return findings


class InvalidToolSelectionDetector(BaseDetector):
    def detect(self, trace: Trace) -> List[FailureFinding]:
        findings: List[FailureFinding] = []
        for index, event in enumerate(trace.events):
            if event.event_type == EventType.TOOL_CALL.value:
                data = event.data or {}
                is_valid = data.get("is_valid")
                error_type = data.get("error_type")

                if is_valid is False or error_type == "invalid_tool":
                    tool_name = data.get("tool_name", "")
                    call_id = data.get("call_id", "")
                    finding = FailureFinding(
                        failure_type=FailureType.INVALID_TOOL_SELECTION.value,
                        severity=Severity.MEDIUM.value,
                        location={"event_id": event.event_id, "event_index": index},
                        evidence={"tool_name": tool_name, "call_id": call_id, "data": data},
                        explanation=f"Invalid tool selection '{tool_name}' at event '{event.event_id}'",
                        confidence=1.0,
                    )
                    findings.append(finding)
        return findings


class UnresolvedToolCallDetector(BaseDetector):
    def detect(self, trace: Trace) -> List[FailureFinding]:
        findings: List[FailureFinding] = []
        tool_calls: Dict[str, Dict[str, Any]] = {}
        resolved_call_ids: Set[str] = set()

        for index, event in enumerate(trace.events):
            if event.event_type == EventType.TOOL_CALL.value:
                call_id = event.data.get("call_id")
                if call_id:
                    tool_calls[call_id] = {
                        "event_id": event.event_id,
                        "event_index": index,
                        "tool_name": event.data.get("tool_name", ""),
                    }
            elif event.event_type == EventType.TOOL_RESULT.value:
                call_id = event.data.get("call_id")
                if call_id:
                    resolved_call_ids.add(call_id)

        total_events = len(trace.events)
        for call_id, info in tool_calls.items():
            if call_id not in resolved_call_ids:
                is_truncated = (info["event_index"] == total_events - 1)
                confidence = 0.70 if is_truncated else 1.0
                explanation = (
                    f"Tool call '{call_id}' for tool '{info['tool_name']}' was not resolved with a tool_result "
                    f"({'trace ends immediately after call' if is_truncated else 'unresolved call in trace'})"
                )

                finding = FailureFinding(
                    failure_type=FailureType.UNRESOLVED_TOOL_CALL.value,
                    severity=Severity.MEDIUM.value,
                    location={"event_id": info["event_id"], "event_index": info["event_index"]},
                    evidence={
                        "call_id": call_id,
                        "tool_name": info["tool_name"],
                        "truncated": is_truncated,
                    },
                    explanation=explanation,
                    confidence=confidence,
                )
                findings.append(finding)

        return findings

