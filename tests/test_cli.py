"""
Tests for Phase 7 — CLI.

Verifies CLI command parsing, input file handling, JSON output formatting,
exit codes, and error states for validate, analyze, reproduce, and verify subcommands.
"""

import json
import pytest
from aifi.cli import create_parser, main


@pytest.fixture
def temp_trace_files(tmp_path):
    # Valid pre-fix trace with tool failure
    pre_trace_data = {
        "run_id": "cli-pre-run",
        "schema_version": "1.0",
        "events": [
            {
                "event_id": "e1",
                "event_type": "tool_call",
                "data": {"tool_name": "calc", "call_id": "c1", "tool_input": {"expr": "1/0"}},
            },
            {
                "event_id": "e2",
                "event_type": "tool_result",
                "data": {"call_id": "c1", "status": "error", "error": "ZeroDivisionError"},
            },
        ],
    }

    # Valid post-fix trace
    post_trace_data = {
        "run_id": "cli-post-run",
        "schema_version": "1.0",
        "events": [
            {
                "event_id": "e1",
                "event_type": "tool_call",
                "data": {"tool_name": "calc", "call_id": "c1", "tool_input": {"expr": "1/1"}},
            },
            {
                "event_id": "e2",
                "event_type": "tool_result",
                "data": {"call_id": "c1", "status": "success", "output": "1"},
            },
        ],
    }

    # Invalid trace (missing run_id)
    invalid_trace_data = {
        "run_id": "",
        "events": [],
    }

    pre_file = tmp_path / "pre.json"
    post_file = tmp_path / "post.json"
    invalid_file = tmp_path / "invalid.json"

    pre_file.write_text(json.dumps(pre_trace_data), encoding="utf-8")
    post_file.write_text(json.dumps(post_trace_data), encoding="utf-8")
    invalid_file.write_text(json.dumps(invalid_trace_data), encoding="utf-8")

    return {
        "pre": str(pre_file),
        "post": str(post_file),
        "invalid": str(invalid_file),
    }


def test_cli_parser_help(capsys):
    parser = create_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "AI Failure Intelligence (AIFI) CLI" in captured.out


def test_cli_main_default(capsys):
    assert main([]) == 0
    captured = capsys.readouterr()
    assert "usage: aifi" in captured.out


def test_cli_validate_success(temp_trace_files, capsys):
    ret = main(["validate", temp_trace_files["pre"]])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["status"] == "valid"


def test_cli_validate_invalid_trace(temp_trace_files, capsys):
    ret = main(["validate", temp_trace_files["invalid"]])
    assert ret == 1
    captured = capsys.readouterr()
    data = json.loads(captured.err)
    assert data["status"] == "invalid"
    assert "error" in data


def test_cli_validate_missing_file(capsys):
    ret = main(["validate", "nonexistent.json"])
    assert ret == 1
    captured = capsys.readouterr()
    data = json.loads(captured.err)
    assert data["status"] == "invalid"


def test_cli_analyze_success(temp_trace_files, capsys):
    ret = main(["analyze", temp_trace_files["pre"]])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["run_id"] == "cli-pre-run"
    assert data["has_failures"] is True
    assert len(data["findings"]) == 1
    assert len(data["diagnoses"]) == 1


def test_cli_reproduce_success(temp_trace_files, capsys):
    ret = main(["reproduce", temp_trace_files["pre"]])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["run_id"] == "cli-pre-run"
    assert len(data["reproductions"]) == 1


def test_cli_verify_success(temp_trace_files, capsys):
    ret = main(["verify", temp_trace_files["pre"], temp_trace_files["post"]])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["pre_run_id"] == "cli-pre-run"
    assert data["post_run_id"] == "cli-post-run"
    assert len(data["verifications"]) == 1
    assert data["verifications"][0]["status"] == "fixed"
