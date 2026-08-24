"""
AI Failure Intelligence (AIFI) — Command-Line Interface.

Provides CLI access to top-level AIFI functions:
- validate
- analyze (detect + diagnose)
- reproduce
- verify

Architectural constraint:
CLI -> Public Python API -> Core Implementation
"""

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

import aifi


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aifi",
        description="AI Failure Intelligence (AIFI) CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 1. validate command
    val_parser = subparsers.add_parser("validate", help="Validate an AIFI trace JSON file")
    val_parser.add_argument("file", help="Path to trace JSON file")

    # 2. analyze command
    anz_parser = subparsers.add_parser("analyze", help="Detect and diagnose failures in a trace JSON file")
    anz_parser.add_argument("file", help="Path to trace JSON file")

    # 3. reproduce command
    rep_parser = subparsers.add_parser("reproduce", help="Attempt reproduction of failures in a trace JSON file (use Python API aifi.reproduce_trace for custom local tool runners)")
    rep_parser.add_argument("file", help="Path to trace JSON file")

    # 4. verify command
    ver_parser = subparsers.add_parser("verify", help="Verify fix between pre-fix and post-fix trace JSON files")
    ver_parser.add_argument("pre_file", help="Path to pre-fix trace JSON file")
    ver_parser.add_argument("post_file", help="Path to post-fix trace JSON file")

    return parser


def _load_json_trace(file_path: str) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def handle_validate(file_path: str) -> int:
    try:
        trace_dict = _load_json_trace(file_path)
        aifi.validate_trace(trace_dict)
        output = {
            "status": "valid",
            "file": file_path,
        }
        print(json.dumps(output, indent=2))
        return 0
    except (FileNotFoundError, json.JSONDecodeError, aifi.TraceValidationError) as err:
        output = {
            "status": "invalid",
            "file": file_path,
            "error": str(err),
        }
        print(json.dumps(output, indent=2), file=sys.stderr)
        return 1


def handle_analyze(file_path: str) -> int:
    try:
        trace_dict = _load_json_trace(file_path)
        trace_obj = aifi.trace_from_dict(trace_dict)
        detection = aifi.detect_failures(trace_obj)
        diagnosis = aifi.diagnose_failures(trace_obj, detection)

        findings_data = []
        for f in detection.findings:
            findings_data.append({
                "failure_type": f.failure_type,
                "severity": f.severity,
                "location": f.location,
                "evidence": f.evidence,
                "explanation": f.explanation,
                "confidence": f.confidence,
            })

        diagnoses_data = []
        for d in diagnosis.diagnoses:
            diagnoses_data.append({
                "failure_type": d.failure_type,
                "likely_cause": d.likely_cause,
                "evidence": d.evidence,
                "inference": d.inference,
                "confidence": d.confidence,
                "is_certain": d.is_certain,
            })

        output = {
            "run_id": trace_obj.run_id,
            "has_failures": detection.has_failures,
            "findings": findings_data,
            "diagnoses": diagnoses_data,
        }
        print(json.dumps(output, indent=2))
        return 0
    except (FileNotFoundError, json.JSONDecodeError, aifi.TraceValidationError) as err:
        output = {"error": str(err)}
        print(json.dumps(output, indent=2), file=sys.stderr)
        return 1


def handle_reproduce(file_path: str) -> int:
    try:
        trace_dict = _load_json_trace(file_path)
        trace_obj = aifi.trace_from_dict(trace_dict)
        repro_results = aifi.reproduce_trace(trace_obj)

        results_data = []
        for r in repro_results:
            results_data.append({
                "failure_type": r.failure_type,
                "status": r.status,
                "reason": r.reason,
                "evidence": r.evidence,
            })

        output = {
            "run_id": trace_obj.run_id,
            "reproductions": results_data,
        }
        print(json.dumps(output, indent=2))
        return 0
    except (FileNotFoundError, json.JSONDecodeError, aifi.TraceValidationError) as err:
        output = {"error": str(err)}
        print(json.dumps(output, indent=2), file=sys.stderr)
        return 1


def handle_verify(pre_file_path: str, post_file_path: str) -> int:
    try:
        pre_dict = _load_json_trace(pre_file_path)
        post_dict = _load_json_trace(post_file_path)

        pre_trace = aifi.trace_from_dict(pre_dict)
        post_trace = aifi.trace_from_dict(post_dict)

        detection = aifi.detect_failures(pre_trace)

        if not detection.findings:
            output = {
                "status": "unable_to_verify",
                "reason": "Pre-fix trace contains no failure findings to verify",
                "verifications": [],
            }
            print(json.dumps(output, indent=2))
            return 0

        verifications_data = []
        for finding in detection.findings:
            req = aifi.VerificationRequest(
                pre_fix_trace=pre_trace,
                post_fix_trace=post_trace,
                finding=finding,
            )
            res = aifi.verify_fix(req)
            verifications_data.append({
                "failure_type": res.failure_type,
                "status": res.status,
                "reason": res.reason,
                "evidence": res.evidence,
            })

        output = {
            "pre_run_id": pre_trace.run_id,
            "post_run_id": post_trace.run_id,
            "verifications": verifications_data,
        }
        print(json.dumps(output, indent=2))
        return 0
    except (FileNotFoundError, json.JSONDecodeError, aifi.TraceValidationError) as err:
        output = {"error": str(err)}
        print(json.dumps(output, indent=2), file=sys.stderr)
        return 1


def main(args: Optional[List[str]] = None) -> int:
    parser = create_parser()
    parsed_args = parser.parse_args(args)

    if parsed_args.command == "validate":
        return handle_validate(parsed_args.file)
    elif parsed_args.command == "analyze":
        return handle_analyze(parsed_args.file)
    elif parsed_args.command == "reproduce":
        return handle_reproduce(parsed_args.file)
    elif parsed_args.command == "verify":
        return handle_verify(parsed_args.pre_file, parsed_args.post_file)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
