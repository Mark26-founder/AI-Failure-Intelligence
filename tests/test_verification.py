"""
Tests for Phase 5 — Fix Verification.

Each test uses real Trace and FailureFinding objects — no mocks.
Tests are organized per failure type, covering:
    - fixed (original failure condition no longer present)
    - not_fixed (original failure condition still present)
    - unable_to_verify (post-fix trace lacks evidence)

Additional cross-cutting tests cover:
    - unknown failure type
    - invalid trace raises error
"""

import pytest

from aifi.detection import detect_failures, FailureType
from aifi.trace import Trace, TraceEvent, EventType
from aifi.verification import (
    VerificationRequest,
    VerificationResult,
    VerificationStatus,
    verify_fix,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _get_finding(trace: Trace, failure_type: str):
    """Return the first finding of a given failure type from detect_failures."""
    result = detect_failures(trace)
    matches = [f for f in result.findings if f.failure_type == failure_type]
    assert matches, f"No {failure_type} finding in trace {trace.run_id}"
    return matches[0]


# ===========================================================================
# tool_execution_failure
# ===========================================================================

class TestToolExecutionFailureVerification:

    def _pre_fix_trace(self) -> Trace:
        """A trace where a tool call fails with an error result."""
        return Trace(
            run_id="pre-tool-fail",
            events=[
                TraceEvent(
                    event_id="e1",
                    event_type=EventType.TOOL_CALL,
                    data={"tool_name": "divide", "call_id": "c1", "tool_input": {"a": 10, "b": 0}},
                ),
                TraceEvent(
                    event_id="e2",
                    event_type=EventType.TOOL_RESULT,
                    data={"call_id": "c1", "status": "error", "error": "ZeroDivisionError"},
                ),
            ],
        )

    def test_fixed_same_call_id_success(self):
        """Post-fix trace uses same call_id and now succeeds → fixed."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.TOOL_EXECUTION_FAILURE.value)

        post = Trace(
            run_id="post-tool-fixed",
            events=[
                TraceEvent(
                    event_id="e1",
                    event_type=EventType.TOOL_CALL,
                    data={"tool_name": "divide", "call_id": "c1", "tool_input": {"a": 10, "b": 2}},
                ),
                TraceEvent(
                    event_id="e2",
                    event_type=EventType.TOOL_RESULT,
                    data={"call_id": "c1", "status": "success", "output": 5},
                ),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.FIXED.value
        assert result.evidence["matched_call_id"] == "c1"

    def test_not_fixed_same_call_id_still_errors(self):
        """Post-fix trace uses same call_id but still returns error → not_fixed."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.TOOL_EXECUTION_FAILURE.value)

        post = Trace(
            run_id="post-tool-not-fixed",
            events=[
                TraceEvent(
                    event_id="e1",
                    event_type=EventType.TOOL_CALL,
                    data={"tool_name": "divide", "call_id": "c1", "tool_input": {"a": 10, "b": 0}},
                ),
                TraceEvent(
                    event_id="e2",
                    event_type=EventType.TOOL_RESULT,
                    data={"call_id": "c1", "status": "error", "error": "ZeroDivisionError"},
                ),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.NOT_FIXED.value
        assert result.evidence["post_fix_error"] == "ZeroDivisionError"

    def test_not_fixed_via_is_error_flag(self):
        """Post-fix result uses is_error=True flag rather than status field → not_fixed."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.TOOL_EXECUTION_FAILURE.value)

        post = Trace(
            run_id="post-tool-is-error",
            events=[
                TraceEvent(
                    event_id="e1",
                    event_type=EventType.TOOL_CALL,
                    data={"tool_name": "divide", "call_id": "c1", "tool_input": {}},
                ),
                TraceEvent(
                    event_id="e2",
                    event_type=EventType.TOOL_RESULT,
                    data={"call_id": "c1", "is_error": True, "output": "Internal error"},
                ),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.NOT_FIXED.value
        assert result.evidence["post_fix_is_error"] is True

    def test_unable_to_verify_no_tool_results(self):
        """Post-fix trace has no tool_result events → unable_to_verify."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.TOOL_EXECUTION_FAILURE.value)

        post = Trace(
            run_id="post-tool-no-results",
            events=[
                TraceEvent(
                    event_id="e1",
                    event_type=EventType.MODEL_CALL,
                    data={"prompt": "hello"},
                ),
                TraceEvent(
                    event_id="e2",
                    event_type=EventType.FINAL_RESULT,
                    data={"output": "done"},
                ),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.UNABLE_TO_VERIFY.value

    def test_fixed_cross_run_sole_result_success(self):
        """
        Post-fix has a different call_id but a single successful tool_result
        for the same tool_name → fixed via tool_name_first_match.
        """
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.TOOL_EXECUTION_FAILURE.value)

        post = Trace(
            run_id="post-tool-cross-run",
            events=[
                TraceEvent(
                    event_id="e1",
                    event_type=EventType.TOOL_CALL,
                    data={"tool_name": "divide", "call_id": "c99", "tool_input": {"a": 10, "b": 2}},
                ),
                TraceEvent(
                    event_id="e2",
                    event_type=EventType.TOOL_RESULT,
                    data={"call_id": "c99", "status": "success", "output": 5},
                ),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.FIXED.value
        # tool_name resolved from pre-fix → cross-run matching uses tool_name_first_match
        assert result.evidence["match_method"] == "tool_name_first_match"

    def test_not_fixed_cross_run_repeated_identical_calls(self):
        """
        Post-fix (cross-run) calls the same tool multiple times with different
        call_ids. The FIRST occurrence fails; a later call succeeds.
        Verification must evaluate only the first occurrence → not_fixed.
        This ensures the first-occurrence rule prevents misattribution.
        """
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.TOOL_EXECUTION_FAILURE.value)

        post = Trace(
            run_id="post-tool-multi-cross",
            events=[
                # First call: still fails
                TraceEvent(
                    event_id="e1",
                    event_type=EventType.TOOL_CALL,
                    data={"tool_name": "divide", "call_id": "c10", "tool_input": {"a": 10, "b": 0}},
                ),
                TraceEvent(
                    event_id="e2",
                    event_type=EventType.TOOL_RESULT,
                    data={"call_id": "c10", "status": "error", "error": "ZeroDivisionError"},
                ),
                # Second call: succeeds (unrelated retry)
                TraceEvent(
                    event_id="e3",
                    event_type=EventType.TOOL_CALL,
                    data={"tool_name": "divide", "call_id": "c11", "tool_input": {"a": 10, "b": 2}},
                ),
                TraceEvent(
                    event_id="e4",
                    event_type=EventType.TOOL_RESULT,
                    data={"call_id": "c11", "status": "success", "output": 5},
                ),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        # First occurrence of "divide" in post-fix still fails → not_fixed
        assert result.status == VerificationStatus.NOT_FIXED.value
        assert result.evidence["match_method"] == "tool_name_first_match"
        assert result.evidence["post_fix_error"] == "ZeroDivisionError"


# ===========================================================================
# repeated_action_loop
# ===========================================================================

class TestRepeatedActionLoopVerification:

    def _pre_fix_trace(self) -> Trace:
        """A trace with a 3-repeat loop on tool 'fetch'."""
        return Trace(
            run_id="pre-loop",
            events=[
                TraceEvent("e1", EventType.TOOL_CALL, {"tool_name": "fetch", "call_id": "c1", "tool_input": {"url": "http://x"}}),
                TraceEvent("e2", EventType.TOOL_RESULT, {"call_id": "c1", "status": "success"}),
                TraceEvent("e3", EventType.TOOL_CALL, {"tool_name": "fetch", "call_id": "c2", "tool_input": {"url": "http://x"}}),
                TraceEvent("e4", EventType.TOOL_RESULT, {"call_id": "c2", "status": "success"}),
                TraceEvent("e5", EventType.TOOL_CALL, {"tool_name": "fetch", "call_id": "c3", "tool_input": {"url": "http://x"}}),
                TraceEvent("e6", EventType.TOOL_RESULT, {"call_id": "c3", "status": "success"}),
            ],
        )

    def test_fixed_loop_broken_different_inputs(self):
        """Post-fix calls same tool but with different inputs each time → fixed."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.REPEATED_ACTION_LOOP.value)

        post = Trace(
            run_id="post-loop-fixed",
            events=[
                TraceEvent("e1", EventType.TOOL_CALL, {"tool_name": "fetch", "call_id": "c1", "tool_input": {"url": "http://x"}}),
                TraceEvent("e2", EventType.TOOL_RESULT, {"call_id": "c1", "status": "success"}),
                TraceEvent("e3", EventType.TOOL_CALL, {"tool_name": "fetch", "call_id": "c2", "tool_input": {"url": "http://y"}}),
                TraceEvent("e4", EventType.TOOL_RESULT, {"call_id": "c2", "status": "success"}),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.FIXED.value
        assert result.evidence["post_fix_max_consecutive"] < finding.evidence["repeat_count"]

    def test_fixed_loop_broken_single_call(self):
        """Post-fix calls the tool only once with the same input → fixed (count=1 < 3)."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.REPEATED_ACTION_LOOP.value)

        post = Trace(
            run_id="post-loop-single",
            events=[
                TraceEvent("e1", EventType.TOOL_CALL, {"tool_name": "fetch", "call_id": "c1", "tool_input": {"url": "http://x"}}),
                TraceEvent("e2", EventType.TOOL_RESULT, {"call_id": "c1", "status": "success"}),
                TraceEvent("e3", EventType.FINAL_RESULT, {"output": "done"}),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.FIXED.value
        assert result.evidence["post_fix_max_consecutive"] == 1

    def test_not_fixed_loop_persists(self):
        """Post-fix still has 3 consecutive identical calls → not_fixed."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.REPEATED_ACTION_LOOP.value)

        post = Trace(
            run_id="post-loop-persists",
            events=[
                TraceEvent("e1", EventType.TOOL_CALL, {"tool_name": "fetch", "call_id": "c1", "tool_input": {"url": "http://x"}}),
                TraceEvent("e2", EventType.TOOL_RESULT, {"call_id": "c1", "status": "success"}),
                TraceEvent("e3", EventType.TOOL_CALL, {"tool_name": "fetch", "call_id": "c2", "tool_input": {"url": "http://x"}}),
                TraceEvent("e4", EventType.TOOL_RESULT, {"call_id": "c2", "status": "success"}),
                TraceEvent("e5", EventType.TOOL_CALL, {"tool_name": "fetch", "call_id": "c3", "tool_input": {"url": "http://x"}}),
                TraceEvent("e6", EventType.TOOL_RESULT, {"call_id": "c3", "status": "success"}),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.NOT_FIXED.value
        assert result.evidence["post_fix_max_consecutive"] >= 3

    def test_unable_to_verify_tool_not_called(self):
        """Post-fix trace never calls the loop tool → unable_to_verify."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.REPEATED_ACTION_LOOP.value)

        post = Trace(
            run_id="post-loop-no-tool",
            events=[
                TraceEvent("e1", EventType.MODEL_CALL, {"prompt": "done differently"}),
                TraceEvent("e2", EventType.FINAL_RESULT, {"output": "ok"}),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.UNABLE_TO_VERIFY.value
        assert result.evidence["post_fix_calls"] == 0


# ===========================================================================
# execution_error_event
# ===========================================================================

class TestExecutionErrorEventVerification:

    def _pre_fix_trace(self) -> Trace:
        return Trace(
            run_id="pre-exec-err",
            events=[
                TraceEvent("e1", EventType.MODEL_CALL, {"prompt": "do work"}),
                TraceEvent("e2", EventType.ERROR, {"error_type": "TimeoutError", "message": "API timeout"}),
            ],
        )

    def test_fixed_no_error_and_final_result(self):
        """Post-fix has no ERROR event and has FINAL_RESULT → fixed."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.EXECUTION_ERROR_EVENT.value)

        post = Trace(
            run_id="post-exec-err-fixed",
            events=[
                TraceEvent("e1", EventType.MODEL_CALL, {"prompt": "do work"}),
                TraceEvent("e2", EventType.FINAL_RESULT, {"output": "completed"}),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.FIXED.value
        assert result.evidence["post_fix_error_count"] == 0
        assert result.evidence["post_fix_has_final_result"] is True

    def test_not_fixed_error_still_present(self):
        """Post-fix still has an ERROR event → not_fixed."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.EXECUTION_ERROR_EVENT.value)

        post = Trace(
            run_id="post-exec-err-not-fixed",
            events=[
                TraceEvent("e1", EventType.MODEL_CALL, {"prompt": "do work"}),
                TraceEvent("e2", EventType.ERROR, {"error_type": "TimeoutError", "message": "Still timing out"}),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.NOT_FIXED.value
        assert result.evidence["post_fix_error_count"] >= 1

    def test_unable_to_verify_no_error_no_final_result(self):
        """
        Post-fix has no ERROR but also no FINAL_RESULT (truncated trace)
        → unable_to_verify.
        """
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.EXECUTION_ERROR_EVENT.value)

        post = Trace(
            run_id="post-exec-err-truncated",
            events=[
                TraceEvent("e1", EventType.MODEL_CALL, {"prompt": "do work"}),
                TraceEvent("e2", EventType.TOOL_CALL, {"tool_name": "calc", "call_id": "c1"}),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.UNABLE_TO_VERIFY.value
        assert result.evidence["post_fix_has_final_result"] is False


# ===========================================================================
# invalid_tool_selection
# ===========================================================================

class TestInvalidToolSelectionVerification:

    def _pre_fix_trace(self) -> Trace:
        return Trace(
            run_id="pre-invalid-tool",
            events=[
                TraceEvent("e1", EventType.TOOL_CALL, {
                    "tool_name": "ghost_tool", "call_id": "c1", "is_valid": False
                }),
            ],
        )

    def test_fixed_original_tool_now_valid(self):
        """
        Post-fix calls the SAME tool ('ghost_tool') without any invalid marker
        → fixed (the specific original selection is now accepted).
        """
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.INVALID_TOOL_SELECTION.value)

        post = Trace(
            run_id="post-invalid-tool-fixed",
            events=[
                TraceEvent("e1", EventType.TOOL_CALL, {
                    "tool_name": "ghost_tool", "call_id": "c2"
                    # no is_valid=False, no error_type="invalid_tool"
                }),
                TraceEvent("e2", EventType.TOOL_RESULT, {
                    "call_id": "c2", "status": "success"
                }),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.FIXED.value
        assert result.evidence["original_tool_name"] == "ghost_tool"
        assert result.evidence["post_fix_invalid_count"] == 0
        assert result.evidence["post_fix_calls_for_original_tool"] == 1

    def test_fixed_original_valid_despite_different_invalid_tool(self):
        """
        Post-fix: 'ghost_tool' is called validly (fixed), but a DIFFERENT
        tool ('other_ghost') is also invalid. Only the original tool matters
        → result must be fixed, not not_fixed.
        """
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.INVALID_TOOL_SELECTION.value)

        post = Trace(
            run_id="post-invalid-tool-different-bad",
            events=[
                # Original tool called validly
                TraceEvent("e1", EventType.TOOL_CALL, {
                    "tool_name": "ghost_tool", "call_id": "c2"
                }),
                TraceEvent("e2", EventType.TOOL_RESULT, {
                    "call_id": "c2", "status": "success"
                }),
                # An unrelated tool is still invalid — must NOT affect verdict
                TraceEvent("e3", EventType.TOOL_CALL, {
                    "tool_name": "other_ghost", "call_id": "c3", "is_valid": False
                }),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.FIXED.value
        assert result.evidence["original_tool_name"] == "ghost_tool"
        assert result.evidence["post_fix_invalid_count"] == 0

    def test_not_fixed_original_tool_still_invalid(self):
        """Post-fix still calls the original tool with is_valid=False → not_fixed."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.INVALID_TOOL_SELECTION.value)

        post = Trace(
            run_id="post-invalid-tool-not-fixed",
            events=[
                TraceEvent("e1", EventType.TOOL_CALL, {
                    "tool_name": "ghost_tool", "call_id": "c1", "is_valid": False
                }),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.NOT_FIXED.value
        assert result.evidence["post_fix_invalid_count"] >= 1
        assert "c1" in result.evidence["post_fix_invalid_call_ids"]

    def test_unable_to_verify_original_tool_not_attempted(self):
        """
        Post-fix never calls 'ghost_tool' (the original failing tool).
        A DIFFERENT invalid tool is present, but that is irrelevant.
        Result must be unable_to_verify — not not_fixed.
        This is rule 7: a different invalid selection must not prove not_fixed.
        """
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.INVALID_TOOL_SELECTION.value)

        post = Trace(
            run_id="post-invalid-tool-different-only",
            events=[
                # Only a DIFFERENT invalid tool — ghost_tool never called
                TraceEvent("e1", EventType.TOOL_CALL, {
                    "tool_name": "other_ghost", "call_id": "c10", "is_valid": False
                }),
                TraceEvent("e2", EventType.TOOL_CALL, {
                    "tool_name": "real_tool", "call_id": "c11"
                }),
                TraceEvent("e3", EventType.TOOL_RESULT, {
                    "call_id": "c11", "status": "success"
                }),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.UNABLE_TO_VERIFY.value
        assert result.evidence["original_tool_name"] == "ghost_tool"
        assert result.evidence["post_fix_calls_for_original_tool"] == 0

    def test_unable_to_verify_no_tool_calls_in_post(self):
        """Post-fix has no tool_call events at all → unable_to_verify."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.INVALID_TOOL_SELECTION.value)

        post = Trace(
            run_id="post-invalid-tool-no-calls",
            events=[
                TraceEvent("e1", EventType.MODEL_CALL, {"prompt": "skip tools"}),
                TraceEvent("e2", EventType.FINAL_RESULT, {"output": "done directly"}),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.UNABLE_TO_VERIFY.value
        assert result.evidence["post_fix_calls_for_original_tool"] == 0


# ===========================================================================
# unresolved_tool_call
# ===========================================================================

class TestUnresolvedToolCallVerification:

    def _pre_fix_trace(self) -> Trace:
        return Trace(
            run_id="pre-unresolved",
            events=[
                TraceEvent("e1", EventType.TOOL_CALL, {"tool_name": "async_job", "call_id": "c100"}),
            ],
        )

    def test_fixed_same_call_id_now_resolved(self):
        """Post-fix same call_id has a matching tool_result → fixed."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.UNRESOLVED_TOOL_CALL.value)

        post = Trace(
            run_id="post-unresolved-fixed",
            events=[
                TraceEvent("e1", EventType.TOOL_CALL, {"tool_name": "async_job", "call_id": "c100"}),
                TraceEvent("e2", EventType.TOOL_RESULT, {"call_id": "c100", "status": "success"}),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.FIXED.value
        assert result.evidence["post_fix_resolved"] is True

    def test_fixed_cross_run_tool_name_resolved(self):
        """Post-fix uses a different call_id for same tool_name but resolves it → fixed."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.UNRESOLVED_TOOL_CALL.value)

        post = Trace(
            run_id="post-unresolved-cross",
            events=[
                TraceEvent("e1", EventType.TOOL_CALL, {"tool_name": "async_job", "call_id": "c200"}),
                TraceEvent("e2", EventType.TOOL_RESULT, {"call_id": "c200", "status": "success"}),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.FIXED.value
        assert result.evidence["match_method"] == "tool_name"

    def test_not_fixed_call_still_unresolved(self):
        """Post-fix calls the same tool but still has no tool_result → not_fixed."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.UNRESOLVED_TOOL_CALL.value)

        post = Trace(
            run_id="post-unresolved-not-fixed",
            events=[
                TraceEvent("e1", EventType.TOOL_CALL, {"tool_name": "async_job", "call_id": "c100"}),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.NOT_FIXED.value
        assert result.evidence["post_fix_resolved"] is False

    def test_unable_to_verify_tool_not_called(self):
        """Post-fix trace never calls the tool at all → unable_to_verify."""
        pre = self._pre_fix_trace()
        finding = _get_finding(pre, FailureType.UNRESOLVED_TOOL_CALL.value)

        post = Trace(
            run_id="post-unresolved-absent",
            events=[
                TraceEvent("e1", EventType.MODEL_CALL, {"prompt": "done"}),
                TraceEvent("e2", EventType.FINAL_RESULT, {"output": "ok"}),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.UNABLE_TO_VERIFY.value


# ===========================================================================
# Cross-cutting: unknown failure type and invalid traces
# ===========================================================================

class TestVerificationCrossCutting:

    def test_unknown_failure_type_returns_unable_to_verify(self):
        """A finding with an unrecognised failure_type → unable_to_verify."""
        from aifi.detection.models import FailureFinding

        finding = FailureFinding(
            failure_type="some_future_type",
            severity="medium",
            location={"event_id": "e1", "event_index": 0},
            evidence={},
            explanation="future failure",
        )
        pre = Trace(
            run_id="pre-unknown",
            events=[TraceEvent("e1", EventType.MODEL_CALL, {"prompt": "x"})],
        )
        post = Trace(
            run_id="post-unknown",
            events=[TraceEvent("e1", EventType.FINAL_RESULT, {"output": "y"})],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert result.status == VerificationStatus.UNABLE_TO_VERIFY.value
        assert "some_future_type" in result.reason

    def test_invalid_pre_fix_trace_raises(self):
        """An invalid pre-fix trace raises TraceValidationError."""
        from aifi.trace import TraceValidationError
        from aifi.detection.models import FailureFinding

        finding = FailureFinding(
            failure_type=FailureType.EXECUTION_ERROR_EVENT.value,
            severity="high",
            location={"event_id": "e1", "event_index": 0},
            evidence={},
            explanation="err",
        )
        # run_id="" is invalid
        bad_pre = Trace(run_id="", events=[TraceEvent("e1", EventType.ERROR, {})])
        good_post = Trace(
            run_id="post-ok",
            events=[TraceEvent("e1", EventType.FINAL_RESULT, {"output": "ok"})],
        )

        with pytest.raises(TraceValidationError):
            verify_fix(VerificationRequest(pre_fix_trace=bad_pre, post_fix_trace=good_post, finding=finding))

    def test_invalid_post_fix_trace_raises(self):
        """An invalid post-fix trace raises TraceValidationError."""
        from aifi.trace import TraceValidationError

        pre = Trace(
            run_id="pre-ok",
            events=[TraceEvent("e1", EventType.ERROR, {"message": "boom"})],
        )
        finding = _get_finding(pre, FailureType.EXECUTION_ERROR_EVENT.value)
        bad_post = Trace(run_id="", events=[TraceEvent("e1", EventType.FINAL_RESULT, {})])

        with pytest.raises(TraceValidationError):
            verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=bad_post, finding=finding))

    def test_verification_result_fields(self):
        """VerificationResult carries failure_type, status, reason, evidence."""
        pre = Trace(
            run_id="pre-fields",
            events=[
                TraceEvent("e1", EventType.ERROR, {"error_type": "OOM", "message": "out of memory"}),
            ],
        )
        finding = _get_finding(pre, FailureType.EXECUTION_ERROR_EVENT.value)
        post = Trace(
            run_id="post-fields",
            events=[
                TraceEvent("e1", EventType.MODEL_CALL, {"prompt": "ok"}),
                TraceEvent("e2", EventType.FINAL_RESULT, {"output": "done"}),
            ],
        )

        result = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert isinstance(result, VerificationResult)
        assert result.failure_type == FailureType.EXECUTION_ERROR_EVENT.value
        assert result.status in {v.value for v in VerificationStatus}
        assert isinstance(result.reason, str) and result.reason
        assert isinstance(result.evidence, dict)

    def test_priority2_same_tool_different_input_succeeds_original_input_fails(self):
        """PRE: tool=calc, input=A -> fail. POST: tool=calc, input=B -> success, input=A -> fail. Verdict: not_fixed."""
        pre = Trace(
            run_id="pre-calc-fail",
            events=[
                TraceEvent("e1", EventType.TOOL_CALL, {"tool_name": "calc", "call_id": "c1", "tool_input": {"op": "div", "x": 1, "y": 0}}),
                TraceEvent("e2", EventType.TOOL_RESULT, {"call_id": "c1", "status": "error", "error": "ZeroDivision"}),
            ],
        )
        finding = _get_finding(pre, FailureType.TOOL_EXECUTION_FAILURE.value)

        post = Trace(
            run_id="post-calc-multi",
            events=[
                # Call B succeeds
                TraceEvent("e1", EventType.TOOL_CALL, {"tool_name": "calc", "call_id": "c_other", "tool_input": {"op": "add", "x": 1, "y": 1}}),
                TraceEvent("e2", EventType.TOOL_RESULT, {"call_id": "c_other", "status": "success", "output": 2}),
                # Call A still fails
                TraceEvent("e3", EventType.TOOL_CALL, {"tool_name": "calc", "call_id": "c_orig", "tool_input": {"op": "div", "x": 1, "y": 0}}),
                TraceEvent("e4", EventType.TOOL_RESULT, {"call_id": "c_orig", "status": "error", "error": "ZeroDivision"}),
            ],
        )

        res = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert res.status == VerificationStatus.NOT_FIXED.value

    def test_priority2_different_tool_succeeds_unable_to_verify(self):
        """PRE: tool=calc -> fail. POST: tool=formatter -> success. Verdict: unable_to_verify."""
        pre = Trace(
            run_id="pre-calc-fail",
            events=[
                TraceEvent("e1", EventType.TOOL_CALL, {"tool_name": "calc", "call_id": "c1", "tool_input": {"x": 10}}),
                TraceEvent("e2", EventType.TOOL_RESULT, {"call_id": "c1", "status": "error", "error": "Fail"}),
            ],
        )
        finding = _get_finding(pre, FailureType.TOOL_EXECUTION_FAILURE.value)

        post = Trace(
            run_id="post-different-tool",
            events=[
                TraceEvent("e1", EventType.TOOL_CALL, {"tool_name": "formatter", "call_id": "c99", "tool_input": {"text": "hi"}}),
                TraceEvent("e2", EventType.TOOL_RESULT, {"call_id": "c99", "status": "success", "output": "HI"}),
            ],
        )

        res = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert res.status == VerificationStatus.UNABLE_TO_VERIFY.value

    def test_priority6_different_operation_execution_error_unable_to_verify(self):
        """PRE: task A error. POST: task B final_result. Verdict: unable_to_verify."""
        pre = Trace(
            run_id="pre-task-a",
            events=[
                TraceEvent("e1", EventType.MODEL_CALL, {"prompt": "task A process data"}),
                TraceEvent("e2", EventType.ERROR, {"error_type": "DataError", "message": "Corrupt data"}),
            ],
            metadata={"task": "task_A"},
        )
        finding = _get_finding(pre, FailureType.EXECUTION_ERROR_EVENT.value)

        post = Trace(
            run_id="post-task-b",
            events=[
                TraceEvent("e1", EventType.MODEL_CALL, {"prompt": "task B generate report"}),
                TraceEvent("e2", EventType.FINAL_RESULT, {"output": "Report generated"}),
            ],
            metadata={"task": "task_B"},
        )

        res = verify_fix(VerificationRequest(pre_fix_trace=pre, post_fix_trace=post, finding=finding))
        assert res.status == VerificationStatus.UNABLE_TO_VERIFY.value

