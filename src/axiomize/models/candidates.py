"""Model candidate records (PHASE 2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CandidateModel:
    model_family: str = ""
    family: str = ""
    structure: str = ""
    variables: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    initial_conditions: dict[str, Any] = field(default_factory=dict)
    boundary_conditions: dict[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    dimensions: dict[str, str] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    expected_domain: str = ""
    required_data: str = ""
    computational_complexity: str = ""
    identifiability: str = ""
    falsification_conditions: list[str] = field(default_factory=list)
    expected_limitations: str = ""

    def validate(self) -> bool:
        missing = [f for f in ("family", "structure", "variables", "parameters",
                               "assumptions", "falsification_conditions")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"candidate model missing: {', '.join(missing)}")
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family or self.model_family,
            "structure": self.structure,
            "variables": self.variables,
            "parameters": self.parameters,
            "initial_conditions": self.initial_conditions,
            "boundary_conditions": self.boundary_conditions,
            "assumptions": self.assumptions,
            "constraints": self.constraints,
            "dimensions": self.dimensions,
            "units": self.units,
            "expected_domain": self.expected_domain,
            "required_data": self.required_data,
            "computational_complexity": self.computational_complexity,
            "identifiability": self.identifiability,
            "falsification_conditions": self.falsification_conditions,
            "expected_limitations": self.expected_limitations,
        }
