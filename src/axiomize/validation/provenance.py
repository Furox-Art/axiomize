"""Value provenance tracking (PHASE 2).

Every important value records where it came from. An LLM guess must
never look like measured data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Provenance(str, Enum):
    USER_PROVIDED = "USER_PROVIDED"
    DATA_FITTED = "DATA_FITTED"
    LITERATURE = "LITERATURE"
    LLM_ASSUMED = "LLM_ASSUMED"
    SOLVER_DERIVED = "SOLVER_DERIVED"
    DERIVED_FROM_OTHER_PARAMETER = "DERIVED_FROM_OTHER_PARAMETER"
    DEFAULT = "DEFAULT"
    ASSUMED_FOR_DEMONSTRATION = "ASSUMED_FOR_DEMONSTRATION"
    UNKNOWN = "UNKNOWN"


_EVIDENCE = {Provenance.USER_PROVIDED, Provenance.DATA_FITTED, Provenance.LITERATURE}


@dataclass
class Parameter:
    name: str
    symbol: str
    unit: str
    value: float | None = None
    provenance: Provenance = Provenance.UNKNOWN
    uncertainty: float | None = None
    source: str = ""


def is_measured(param: Parameter) -> bool:
    """True only for evidence-grade provenance, never for LLM assumptions."""
    return param.provenance in _EVIDENCE
