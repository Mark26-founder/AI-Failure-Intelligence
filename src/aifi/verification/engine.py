"""
Fix Verification Engine — Phase 5

Given a pre-fix trace and a post-fix trace, determines whether the failure
identified by a specific FailureFinding was resolved.

Verification rules are explicit, deterministic, and operate on observable
trace structure — not on raw text comparison or event counts.

Supported failure types:
    tool_execution_failure    — compare relevant tool operation outcome
    repeated_action_loop      — compare repeat count for same tool+input
    execution_error_event     — compare presence of ERROR events vs. FINAL_RESULT
    invalid_tool_selection    — check original tool_name validity in post-fix
    unresolved_tool_call      — compare whether the tool call received a result

All other failure types → unable_to_verify (no rule defined).
"""

from typing import Any, Dict, List, Set

from aifi.detection.models import FailureFinding, FailureType
from aifi.trace.schema import Trace, EventType
from aifi.trace.validator import validate_trace
from aifi.verification.models import VerificationRequest, VerificationResult, VerificationStatus


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def verify_fix(request: VerificationRequest) -> VerificationResult:
    """
    Determine whether the failure in request.finding was resolved between
    request.pre_fix_trace and request.post_fix_trace.

    Both traces are validated before comparison.
    """
    validate_trace(request.pre_fix_trace)
    validate_trace(request.post_fix_trace)

    ftype = request.finding.failure_type
    post = request.post_fix_trace

    if ftype == FailureType.TOOL_EXECUTION_FAILURE.value:
        return _verify_tool_execution_failure(request.finding, request.pre_fix_trace, post)
    elif ftype == FailureType.REPEATED_ACTION_LOOP.value:
        return _verify_repeated_action_loop(request.finding, post)
    elif ftype == FailureType.EXECUTION_ERROR_EVENT.value:
        return _verify_execution_error_event(request.finding, request.pre_fix_trace, post)
    elif ftype == FailureType.INVALID_TOOL_SELECTION.value:
        return _verify_invalid_tool_selection(request.finding, post)
    elif ftype == FailureType.UNRESOLVED_TOOL_CALL.value:
        return _verify_unresolved_tool_call(request.finding, request.pre_fix_trace, post)
    else:
        return VerificationResult(
            failure_type=ftype,
            status=VerificationStatus.UNABLE_TO_VERIFY.value,
            reason=f"No verification rule is defined for failure type '{ftype}'",
            evidence={},
        )


# ---------------------------------------------------------------------------
# Rule: tool_execution_failure
#
# Fixed:
#   The relevant tool operation (matched by call_id first, then by tool_name
#   for cross-run scenarios) was executed in the post-fix trace AND its
#   tool_result does not indicate an error.
#
# Not fixed:
#   The relevant tool operation was executed AND its tool_result still
#   indicates an error.
#
# Unable to verify:
#   The relevant tool operation was not attempted in the post-fix trace,
#   so there is no post-fix evidence about the outcome.
#
# Cross-run matching (when call_ids differ between runs):
#   The original tool_name is resolved from the pre-fix trace TOOL_CALL event
#   that owns the failing call_id.  The post-fix trace is then searched for
#   the FIRST TOOL_CALL for that tool_name (by event order), and only that
#   specific call's result is evaluated.  This prevents accidental attribution
#   to an unrelated later invocation of the same tool.
# ---------------------------------------------------------------------------

def _verify_tool_execution_failure(
    finding: FailureFinding,
    pre: Trace,
    post: Trace,
) -> VerificationResult:
    ftype = finding.failure_type
    orig_call_id: str = finding.evidence.get("call_id", "")

    # Step 1: Resolve original tool_name and tool_input from the pre-fix TOOL_CALL event.
    orig_tool_name: str = ""
    orig_tool_input: Dict[str, Any] = {}
    for evt in pre.events:
        if (
            evt.event_type == EventType.TOOL_CALL.value
            and evt.data.get("call_id") == orig_call_id
        ):
            orig_tool_name = evt.data.get("tool_name", "")
            orig_tool_input = evt.data.get("tool_input", {})
            break

    # Step 2: Collect post-fix tool results keyed by call_id.
    post_results: Dict[str, Dict[str, Any]] = {}
    for evt in post.events:
        if evt.event_type == EventType.TOOL_RESULT.value:
            cid = evt.data.get("call_id", "")
            if cid:
                post_results[cid] = evt.data

    if not post_results:
        return VerificationResult(
            failure_type=ftype,
            status=VerificationStatus.UNABLE_TO_VERIFY.value,
            reason="Post-fix trace contains no tool_result events; the relevant tool operation was not observed",
            evidence={"original_call_id": orig_call_id, "original_tool_name": orig_tool_name},
        )

    # Step 3: Exact call_id match.
    if orig_call_id and orig_call_id in post_results:
        result_data = post_results[orig_call_id]
        return _evaluate_tool_result(ftype, orig_call_id, result_data, match_method="call_id")

    # Step 4: Cross-run matching by tool_name + tool_input.
    if orig_tool_name:
        same_tool_calls = [
            evt for evt in post.events
            if evt.event_type == EventType.TOOL_CALL.value and evt.data.get("tool_name") == orig_tool_name
        ]

        if not same_tool_calls:
            return VerificationResult(
                failure_type=ftype,
                status=VerificationStatus.UNABLE_TO_VERIFY.value,
                reason=(
                    f"Tool '{orig_tool_name}' was not called in the post-fix trace; "
                    "cannot confirm whether the failure was resolved"
                ),
                evidence={
                    "original_call_id": orig_call_id,
                    "original_tool_name": orig_tool_name,
                    "post_fix_tool_result_count": len(post_results),
                },
            )

        # 4a: Look for calls with matching input
        matching_input_calls = [
            evt for evt in same_tool_calls
            if orig_tool_input and evt.data.get("tool_input", {}) == orig_tool_input
        ]

        if matching_input_calls:
            for evt in matching_input_calls:
                cid = evt.data.get("call_id", "")
                if cid in post_results:
                    res = post_results[cid]
                    if res.get("status") == "error" or res.get("is_error") is True or bool(res.get("error")):
                        return _evaluate_tool_result(ftype, cid, res, match_method="tool_name_first_match")

            first_matching_cid = matching_input_calls[0].data.get("call_id", "")
            if first_matching_cid in post_results:
                return _evaluate_tool_result(
                    ftype, first_matching_cid, post_results[first_matching_cid], match_method="tool_name_first_match"
                )

        # 4b: If no exact input match, check if any call to same_tool_name is still failing
        for evt in same_tool_calls:
            cid = evt.data.get("call_id", "")
            if cid in post_results:
                res = post_results[cid]
                if res.get("status") == "error" or res.get("is_error") is True or bool(res.get("error")):
                    return _evaluate_tool_result(ftype, cid, res, match_method="tool_name_first_match")

        # 4c: All calls to same_tool_name succeeded
        first_cid = same_tool_calls[0].data.get("call_id", "")
        if first_cid in post_results:
            return _evaluate_tool_result(
                ftype, first_cid, post_results[first_cid], match_method="tool_name_first_match"
            )

    # Step 5: tool_name unknown
    if len(post_results) == 1:
        sole_cid, sole_data = next(iter(post_results.items()))
        return _evaluate_tool_result(ftype, sole_cid, sole_data, match_method="sole_result")

    return VerificationResult(
        failure_type=ftype,
        status=VerificationStatus.UNABLE_TO_VERIFY.value,
        reason=(
            "Cannot attribute a specific post-fix result to the original failure: "
            "call_id does not match and tool_name could not be resolved from the pre-fix trace"
        ),
        evidence={
            "original_call_id": orig_call_id,
            "post_fix_tool_result_count": len(post_results),
        },
    )


def _evaluate_tool_result(
    ftype: str,
    call_id: str,
    result_data: Dict[str, Any],
    match_method: str,
) -> VerificationResult:
    """Return fixed/not_fixed based on a specific tool_result event's data."""
    status = result_data.get("status")
    is_error = result_data.get("is_error")
    error_content = result_data.get("error")

    still_failing = (
        status == "error"
        or is_error is True
        or bool(error_content)
    )

    if still_failing:
        return VerificationResult(
            failure_type=ftype,
            status=VerificationStatus.NOT_FIXED.value,
            reason=f"Tool operation (call_id='{call_id}') still returns an error in the post-fix trace",
            evidence={
                "matched_call_id": call_id,
                "match_method": match_method,
                "post_fix_status": status,
                "post_fix_is_error": is_error,
                "post_fix_error": error_content,
            },
        )
    else:
        return VerificationResult(
            failure_type=ftype,
            status=VerificationStatus.FIXED.value,
            reason=f"Tool operation (call_id='{call_id}') completed without error in the post-fix trace",
            evidence={
                "matched_call_id": call_id,
                "match_method": match_method,
                "post_fix_status": status,
                "post_fix_is_error": is_error,
                "post_fix_error": error_content,
            },
        )


def _verify_repeated_action_loop(
    finding: FailureFinding,
    post: Trace,
) -> VerificationResult:
    ftype = finding.failure_type
    orig_tool_name: str = finding.evidence.get("tool_name", "")
    orig_tool_input: Dict[str, Any] = finding.evidence.get("tool_input", {})
    orig_repeat_count: int = finding.evidence.get("repeat_count", 3)

    post_max_consecutive, post_total_calls = _count_consecutive(
        post, orig_tool_name, orig_tool_input
    )

    if post_total_calls == 0:
        return VerificationResult(
            failure_type=ftype,
            status=VerificationStatus.UNABLE_TO_VERIFY.value,
            reason=(
                f"Tool '{orig_tool_name}' with the original input was never called "
                "in the post-fix trace; cannot confirm the loop condition was addressed"
            ),
            evidence={
                "original_tool_name": orig_tool_name,
                "original_tool_input": orig_tool_input,
                "original_repeat_count": orig_repeat_count,
                "post_fix_calls": 0,
                "post_fix_max_consecutive": 0,
            },
        )

    threshold = orig_repeat_count

    if post_max_consecutive >= threshold:
        return VerificationResult(
            failure_type=ftype,
            status=VerificationStatus.NOT_FIXED.value,
            reason=(
                f"Post-fix trace still shows {post_max_consecutive} consecutive identical "
                f"calls to '{orig_tool_name}' (threshold: {threshold})"
            ),
            evidence={
                "original_tool_name": orig_tool_name,
                "original_tool_input": orig_tool_input,
                "original_repeat_count": orig_repeat_count,
                "post_fix_max_consecutive": post_max_consecutive,
                "post_fix_total_calls": post_total_calls,
                "threshold": threshold,
            },
        )
    else:
        return VerificationResult(
            failure_type=ftype,
            status=VerificationStatus.FIXED.value,
            reason=(
                f"Post-fix trace shows at most {post_max_consecutive} consecutive identical "
                f"call(s) to '{orig_tool_name}' — below the threshold of {threshold}"
            ),
            evidence={
                "original_tool_name": orig_tool_name,
                "original_tool_input": orig_tool_input,
                "original_repeat_count": orig_repeat_count,
                "post_fix_max_consecutive": post_max_consecutive,
                "post_fix_total_calls": post_total_calls,
                "threshold": threshold,
            },
        )


def _count_consecutive(
    trace: Trace, tool_name: str, tool_input: Dict[str, Any]
) -> tuple:
    max_consecutive = 0
    current_run = 0
    total_calls = 0

    for evt in trace.events:
        if evt.event_type == EventType.TOOL_CALL.value:
            tn = evt.data.get("tool_name", "")
            ti = evt.data.get("tool_input", {})
            if tn == tool_name and ti == tool_input:
                total_calls += 1
                current_run += 1
                if current_run > max_consecutive:
                    max_consecutive = current_run
            else:
                current_run = 0

    return max_consecutive, total_calls


def _verify_execution_error_event(
    finding: FailureFinding,
    pre: Trace,
    post: Trace,
) -> VerificationResult:
    ftype = finding.failure_type

    # Verify scenario attribution between pre and post
    if not _is_same_execution_scenario(pre, post):
        return VerificationResult(
            failure_type=ftype,
            status=VerificationStatus.UNABLE_TO_VERIFY.value,
            reason="Post-fix trace cannot be attributed to original failed scenario (different operation or prompt)",
            evidence={"pre_run_id": pre.run_id, "post_run_id": post.run_id},
        )

    post_error_events = [
        evt for evt in post.events
        if evt.event_type == EventType.ERROR.value
    ]
    post_final_result_events = [
        evt for evt in post.events
        if evt.event_type == EventType.FINAL_RESULT.value
    ]

    has_post_error = len(post_error_events) > 0
    has_post_final = len(post_final_result_events) > 0

    if has_post_error:
        return VerificationResult(
            failure_type=ftype,
            status=VerificationStatus.NOT_FIXED.value,
            reason=(
                f"Post-fix trace still contains {len(post_error_events)} error event(s)"
            ),
            evidence={
                "post_fix_error_count": len(post_error_events),
                "post_fix_error_event_ids": [e.event_id for e in post_error_events],
                "post_fix_has_final_result": has_post_final,
            },
        )

    if not has_post_final:
        return VerificationResult(
            failure_type=ftype,
            status=VerificationStatus.UNABLE_TO_VERIFY.value,
            reason=(
                "Post-fix trace contains no error events but also no final_result event; "
                "execution completion cannot be confirmed from an incomplete trace"
            ),
            evidence={
                "post_fix_error_count": 0,
                "post_fix_has_final_result": False,
            },
        )

    return VerificationResult(
        failure_type=ftype,
        status=VerificationStatus.FIXED.value,
        reason=(
            "Post-fix trace contains no error events and execution reached a final_result"
        ),
        evidence={
            "post_fix_error_count": 0,
            "post_fix_has_final_result": True,
            "post_fix_final_result_event_ids": [e.event_id for e in post_final_result_events],
        },
    )


def _is_same_execution_scenario(pre: Trace, post: Trace) -> bool:
    """Check whether pre and post traces share comparable execution scenario."""
    # 1. Metadata scenario check if explicitly set
    pre_task = pre.metadata.get("task") or pre.metadata.get("scenario") or pre.metadata.get("prompt")
    post_task = post.metadata.get("task") or post.metadata.get("scenario") or post.metadata.get("prompt")
    if pre_task and post_task and pre_task != post_task:
        return False

    # 2. Prompt match check if MODEL_CALL events exist
    pre_prompts = [
        e.data.get("prompt") for e in pre.events
        if e.event_type == EventType.MODEL_CALL.value and e.data.get("prompt")
    ]
    post_prompts = [
        e.data.get("prompt") for e in post.events
        if e.event_type == EventType.MODEL_CALL.value and e.data.get("prompt")
    ]
    if pre_prompts and post_prompts:
        if pre_prompts[0] != post_prompts[0]:
            return False

    # 3. Tool operation check if pre had specific tool calls
    pre_tools = {
        e.data.get("tool_name") for e in pre.events
        if e.event_type == EventType.TOOL_CALL.value and e.data.get("tool_name")
    }
    post_tools = {
        e.data.get("tool_name") for e in post.events
        if e.event_type == EventType.TOOL_CALL.value and e.data.get("tool_name")
    }
    if pre_tools and post_tools and not pre_tools.intersection(post_tools):
        return False

    return True


def _verify_invalid_tool_selection(
    finding: FailureFinding,
    post: Trace,
) -> VerificationResult:
    ftype = finding.failure_type
    orig_tool_name: str = finding.evidence.get("tool_name", "")

    orig_tool_calls_in_post = [
        evt for evt in post.events
        if (
            evt.event_type == EventType.TOOL_CALL.value
            and evt.data.get("tool_name") == orig_tool_name
        )
    ]

    if not orig_tool_calls_in_post:
        return VerificationResult(
            failure_type=ftype,
            status=VerificationStatus.UNABLE_TO_VERIFY.value,
            reason=(
                f"Tool '{orig_tool_name}' was not called in the post-fix trace; "
                "cannot confirm whether the invalid selection was corrected"
            ),
            evidence={
                "original_tool_name": orig_tool_name,
                "post_fix_calls_for_original_tool": 0,
            },
        )

    invalid_calls = [
        evt for evt in orig_tool_calls_in_post
        if (
            evt.data.get("is_valid") is False
            or evt.data.get("error_type") == "invalid_tool"
        )
    ]

    if invalid_calls:
        return VerificationResult(
            failure_type=ftype,
            status=VerificationStatus.NOT_FIXED.value,
            reason=(
                f"Tool '{orig_tool_name}' is still marked as invalid in "
                f"{len(invalid_calls)} post-fix call(s)"
            ),
            evidence={
                "original_tool_name": orig_tool_name,
                "post_fix_calls_for_original_tool": len(orig_tool_calls_in_post),
                "post_fix_invalid_count": len(invalid_calls),
                "post_fix_invalid_call_ids": [
                    evt.data.get("call_id", "") for evt in invalid_calls
                ],
            },
        )

    return VerificationResult(
        failure_type=ftype,
        status=VerificationStatus.FIXED.value,
        reason=(
            f"Tool '{orig_tool_name}' was called in the post-fix trace "
            "without any invalid marker"
        ),
        evidence={
            "original_tool_name": orig_tool_name,
            "post_fix_calls_for_original_tool": len(orig_tool_calls_in_post),
            "post_fix_invalid_count": 0,
        },
    )


def _verify_unresolved_tool_call(
    finding: FailureFinding,
    pre: Trace,
    post: Trace,
) -> VerificationResult:
    ftype = finding.failure_type
    orig_call_id: str = finding.evidence.get("call_id", "")
    orig_tool_name: str = finding.evidence.get("tool_name", "")

    # Extract original tool_input from pre-fix trace if available
    orig_tool_input: Dict[str, Any] = {}
    for evt in pre.events:
        if evt.event_type == EventType.TOOL_CALL.value and evt.data.get("call_id") == orig_call_id:
            orig_tool_input = evt.data.get("tool_input", {})
            break

    # Build maps from post-fix trace
    post_call_ids: Set[str] = set()
    post_resolved_call_ids: Set[str] = set()

    for evt in post.events:
        if evt.event_type == EventType.TOOL_CALL.value:
            cid = evt.data.get("call_id", "")
            if cid:
                post_call_ids.add(cid)
        elif evt.event_type == EventType.TOOL_RESULT.value:
            cid = evt.data.get("call_id", "")
            if cid:
                post_resolved_call_ids.add(cid)

    # Try exact call_id match first
    if orig_call_id and orig_call_id in post_call_ids:
        resolved = orig_call_id in post_resolved_call_ids
        if resolved:
            return VerificationResult(
                failure_type=ftype,
                status=VerificationStatus.FIXED.value,
                reason=f"Tool call '{orig_call_id}' now has a matching tool_result in the post-fix trace",
                evidence={
                    "matched_call_id": orig_call_id,
                    "match_method": "call_id",
                    "post_fix_resolved": True,
                },
            )
        else:
            return VerificationResult(
                failure_type=ftype,
                status=VerificationStatus.NOT_FIXED.value,
                reason=f"Tool call '{orig_call_id}' still has no matching tool_result in the post-fix trace",
                evidence={
                    "matched_call_id": orig_call_id,
                    "match_method": "call_id",
                    "post_fix_resolved": False,
                },
            )

    # Cross-run: match by tool_name + tool_input
    if orig_tool_name:
        matching_calls = [
            evt for evt in post.events
            if evt.event_type == EventType.TOOL_CALL.value
            and evt.data.get("tool_name") == orig_tool_name
            and (evt.data.get("tool_input", {}) == orig_tool_input or not orig_tool_input)
        ]

        if matching_calls:
            for evt in matching_calls:
                cid = evt.data.get("call_id", "")
                resolved = cid in post_resolved_call_ids if cid else False
                if resolved:
                    return VerificationResult(
                        failure_type=ftype,
                        status=VerificationStatus.FIXED.value,
                        reason=(
                            f"Tool '{orig_tool_name}' call now has a matching tool_result "
                            "in the post-fix trace"
                        ),
                        evidence={
                            "original_call_id": orig_call_id,
                            "post_fix_call_id": cid,
                            "match_method": "tool_name",
                            "post_fix_resolved": True,
                        },
                    )
                else:
                    return VerificationResult(
                        failure_type=ftype,
                        status=VerificationStatus.NOT_FIXED.value,
                        reason=(
                            f"Tool '{orig_tool_name}' is still called without a matching "
                            "tool_result in the post-fix trace"
                        ),
                        evidence={
                            "original_call_id": orig_call_id,
                            "post_fix_call_id": cid,
                            "match_method": "tool_name",
                            "post_fix_resolved": False,
                        },
                    )

    return VerificationResult(
        failure_type=ftype,
        status=VerificationStatus.UNABLE_TO_VERIFY.value,
        reason=(
            f"Tool '{orig_tool_name}' (call_id='{orig_call_id}') with matching input was not called "
            "in the post-fix trace; cannot confirm whether the unresolved call was addressed"
        ),
        evidence={
            "original_call_id": orig_call_id,
            "original_tool_name": orig_tool_name,
        },
    )

