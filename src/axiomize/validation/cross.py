"""Independent cross-validation (PHASE 2).

The same result computed two independent ways must agree. On mismatch
neither side is silently picked: status CONFLICT with the difference
and a recommended action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from axiomize.validation.status import ValidationStatus


@dataclass
class CrossResult:
    status: ValidationStatus
    primary_result: Any
    verification_result: Any
    difference: Any
    recommended_action: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "primary_result": self.primary_result,
            "verification_result": self.verification_result,
            "difference": self.difference,
            "recommended_action": self.recommended_action,
        }


def compare_values(primary: float, verification: float, tolerance: float,
                   name: str = "result") -> CrossResult:
    diff = abs(primary - verification)
    if diff <= tolerance:
        return CrossResult(ValidationStatus.PASS, primary, verification, diff, [])
    return CrossResult(
        ValidationStatus.CONFLICT, primary, verification, diff,
        [(f"{name}: independent methods disagree by {diff:.4g} (> {tolerance}); "
          "tighten tolerances, check scaling, then investigate model structure")],
    )


def unavailable(tool: str) -> CrossResult:
    return CrossResult(
        ValidationStatus.TOOL_UNAVAILABLE, None, None, None,
        [f"{tool} is not installed; install it or accept the degraded fallback"],
    )
