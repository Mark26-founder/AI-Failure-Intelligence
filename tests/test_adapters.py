"""
Tests for Phase 8 — Adapters and Architectural Boundary.

Verifies:
1. GenericAdapter converts structured data into a valid AIFI Trace.
2. GenericAdapter rejects malformed/invalid inputs with AdapterValidationError.
3. Core analysis (validate, detect, diagnose) works cleanly on adapter-produced traces.
4. Static isolation verification: core modules (trace, detection, diagnosis, reproduction, verification)
   do NOT import or depend on the adapters package.
"""

import os
import sys
import pytest

from aifi import (
    GenericAdapter,
    AdapterValidationError,
    validate_trace,
    detect_failures,
    diagnose_failures,
    Trace,
)


def test_generic_adapter_valid_input():
    adapter = GenericAdapter()
    external_data = {
        "run_id": "adapter-run-1",
        "schema_version": "1.0",
        "events": [
            {
                "event_id": "e1",
                "event_type": "model_call",
                "data": {"prompt": "Run calc"},
            },
            {
                "event_id": "e2",
                "event_type": "tool_call",
                "data": {"tool_name": "calc", "call_id": "c1", "tool_input": {"expr": "1/0"}},
            },
            {
                "event_id": "e3",
                "event_type": "tool_result",
                "data": {"call_id": "c1", "status": "error", "error": "ZeroDivisionError"},
            },
        ],
    }

    trace = adapter.adapt(external_data)
    assert isinstance(trace, Trace)
    assert trace.run_id == "adapter-run-1"
    assert len(trace.events) == 3

    # Validate output trace using core validator
    validate_trace(trace)

    # Pass trace through core failure detection and diagnosis
    detection = detect_failures(trace)
    assert detection.has_failures is True
    assert len(detection.findings) == 1

    diagnosis = diagnose_failures(trace, detection)
    assert len(diagnosis.diagnoses) == 1
    assert "ZeroDivisionError" in diagnosis.diagnoses[0].likely_cause


def test_generic_adapter_invalid_input_types():
    adapter = GenericAdapter()

    # Non-dict input
    with pytest.raises(AdapterValidationError):
        adapter.adapt("not a dict")  # type: ignore

    # Missing run_id
    with pytest.raises(AdapterValidationError):
        adapter.adapt({"run_id": "", "events": []})

    # Unsupported event type
    with pytest.raises(AdapterValidationError):
        adapter.adapt({
            "run_id": "bad-run",
            "events": [{"event_id": "e1", "event_type": "unsupported_type", "data": {}}],
        })


def test_architecture_isolation_core_does_not_import_adapters():
    """
    Static architectural test: Ensure core modules do NOT import from aifi.adapters.
    """
    import importlib
    import pkgutil
    import aifi.trace
    import aifi.detection
    import aifi.diagnosis
    import aifi.reproduction
    import aifi.verification

    core_modules = [
        "aifi.trace",
        "aifi.detection",
        "aifi.diagnosis",
        "aifi.reproduction",
        "aifi.verification",
    ]

    for mod_name in core_modules:
        mod = sys.modules[mod_name]
        pkg_path = getattr(mod, "__path__", None)
        if pkg_path:
            for _, submod_name, _ in pkgutil.walk_packages(pkg_path, prefix=mod_name + "."):
                submod = importlib.import_module(submod_name)
                with open(submod.__file__, "r", encoding="utf-8") as f:
                    content = f.read()
                    assert "aifi.adapters" not in content, f"Architecture violation: core module {submod_name} imports aifi.adapters"
