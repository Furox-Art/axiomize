"""Rule-based Scientific Tool Router (PHASE 1).

Classifies a problem from explicit signals and selects only tools whose
``availability()`` probe really passes. A missing primary backend yields
an alternative or an explicit TOOL_UNAVAILABLE - never a faked result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from axiomize.tools.numerical.scipy_tool import SciPyTool
from axiomize.tools.symbolic.sympy_tool import SymPyTool
from axiomize.validation.status import ValidationStatus

# signal -> (problem_type, primary, verification, reason)
_RULES: list[tuple[frozenset[str], str, list[str], list[str], str]] = [
    (frozenset({"ode", "compartmental"}), "compartmental_ode",
     ["scipy"], ["sympy"],
     "compartmental ODE dynamics solve numerically; closed-form theory verifies"),
    (frozenset({"ode"}), "generic_ode",
     ["scipy"], ["sympy"],
     "time-evolution structure maps to numerical integration"),
    (frozenset({"regression", "data"}), "regression_fit",
     ["scipy"], ["sympy"],
     "curve fitting via least squares with symbolic residual checks"),
    (frozenset({"optimization", "convex"}), "convex_optimization",
     ["scipy"], ["sympy"],
     "convex objective currently falls back to scipy; cvxpy adapter planned"),
    (frozenset({"optimization"}), "generic_optimization",
     ["scipy"], [],
     "constrained optimization falls back to scipy pending casadi adapter"),
    (frozenset({"pde", "fem"}), "pde_fem",
     ["fenics"], ["sympy"],
     "PDE/FEM needs FEniCS which is not pip-installable on all platforms"),
    (frozenset({"bayesian"}), "bayesian_estimation",
     ["pymc"], ["scipy"],
     "Bayesian inference needs PyMC; frequentist fit is the fallback"),
    (frozenset({"network"}), "network_dynamics",
     ["networkx"], ["scipy"],
     "graph structure needs NetworkX; numerical solver verifies dynamics"),
    (frozenset({"logic", "constraints"}), "constraint_verification",
     ["z3"], ["sympy"],
     "logical constraints need Z3; symbolic consistency is the fallback"),
]

_TOOL_CLASSES = {"scipy": SciPyTool, "sympy": SymPyTool}


@dataclass
class ToolDecision:
    problem_type: str
    primary_tools: list[str]
    verification_tools: list[str]
    reason: str
    alternatives: list[str] = field(default_factory=list)
    status: ValidationStatus = ValidationStatus.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem_type": self.problem_type,
            "primary_tools": self.primary_tools,
            "verification_tools": self.verification_tools,
            "reason": self.reason,
            "alternatives": self.alternatives,
            "status": self.status.value,
        }


def _is_available(name: str) -> bool:
    cls = _TOOL_CLASSES.get(name)
    if cls is None:
        return False
    return cls.availability().available


def classify(problem: dict[str, Any]) -> ToolDecision:
    signals = frozenset(s.lower() for s in problem.get("signals", []))
    best: tuple[frozenset[str], str, list[str], list[str], str] | None = None
    for rule in _RULES:
        keys = rule[0]
        if keys <= signals and (best is None or len(keys) > len(best[0])):
            best = rule
    if best is None:
        return ToolDecision(problem_type="unknown", primary_tools=[],
                            verification_tools=[], reason="no rule matched the signals",
                            status=ValidationStatus.INCONCLUSIVE)
    _, problem_type, primary, verification, reason = best
    chosen = [t for t in primary if _is_available(t)]
    missing = [t for t in primary if t not in chosen]
    verified = [t for t in verification if _is_available(t)]
    alternatives = [f"{t}:TOOL_UNAVAILABLE" for t in missing]
    if not chosen:
        fallback = "scipy" if _is_available("scipy") else None
        if fallback and fallback not in verified:
            chosen = [fallback]
            alternatives.append(f"{fallback}:degraded-fallback")
            status = ValidationStatus.WARNING
        else:
            status = ValidationStatus.TOOL_UNAVAILABLE
        return ToolDecision(problem_type, chosen, verified, reason, alternatives, status)
    status = ValidationStatus.WARNING if missing else ValidationStatus.PASS
    return ToolDecision(problem_type, chosen, verified, reason, alternatives, status)
