"""
AI Failure Intelligence (AIFI) — Root Public Package API.

Provides top-level imports for the primary AIFI entities and operations,
eliminating the need to navigate internal module hierarchies.
"""

from aifi.trace import (
    Trace,
    TraceEvent,
    EventType,
    validate_trace,
    load_trace_json,
    dump_trace_json,
    trace_to_dict,
    trace_from_dict,
    TraceValidationError,
)
from aifi.detection import (
    detect_failures,
    DetectionResult,
    FailureFinding,
    FailureType,
    Severity,
)
from aifi.diagnosis import (
    diagnose_failures,
    DiagnosisResult,
    DiagnosisFinding,
)
from aifi.reproduction import (
    reproduce_trace,
    reproduce_failure,
    ReproductionResult,
    ReproductionStatus,
)
from aifi.verification import (
    verify_fix,
    VerificationRequest,
    VerificationResult,
    VerificationStatus,
)
from aifi.adapters import (
    BaseAdapter,
    GenericAdapter,
    AdapterValidationError,
)

__version__ = "0.1.0"

__all__ = [
    # Package Metadata
    "__version__",
    # Trace
    "Trace",
    "TraceEvent",
    "EventType",
    "validate_trace",
    "load_trace_json",
    "dump_trace_json",
    "trace_to_dict",
    "trace_from_dict",
    "TraceValidationError",
    # Detection
    "detect_failures",
    "DetectionResult",
    "FailureFinding",
    "FailureType",
    "Severity",
    # Diagnosis
    "diagnose_failures",
    "DiagnosisResult",
    "DiagnosisFinding",
    # Reproduction
    "reproduce_trace",
    "reproduce_failure",
    "ReproductionResult",
    "ReproductionStatus",
    # Verification
    "verify_fix",
    "VerificationRequest",
    "VerificationResult",
    "VerificationStatus",
    # Adapters
    "BaseAdapter",
    "GenericAdapter",
    "AdapterValidationError",
]
