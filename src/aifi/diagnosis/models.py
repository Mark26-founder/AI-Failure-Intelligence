from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DiagnosisFinding:
    failure_type: str
    likely_cause: str
    evidence: List[str]
    inference: str
    confidence: float = 1.0
    is_certain: bool = True


@dataclass
class DiagnosisResult:
    run_id: str
    diagnoses: List[DiagnosisFinding] = field(default_factory=list)
