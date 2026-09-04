"""Rule-based Scientific Tool Router (PHASE 1).

Classifies a problem from explicit signals and selects only tools whose
availability probe really passes. Missing backends are reported explicitly;
Axiomize never pretends an unavailable verifier ran.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import Any

from axiomize.formal.lean_adapter import LeanAdapter
from axiomize.tools.logic.z3_tool import Z3Tool
from axiomize.tools.numerical.scipy_tool import SciPyTool
from axiomize.tools.optimization.casadi_tool import CasadiTool
from axiomize.tools.optimization.cvxpy_tool import CvxpyTool
from axiomize.tools.statistics.statsmodels_tool import StatsmodelsTool
from axiomize.tools.symbolic.sympy_tool import SymPyTool
from axiomize.validation.status import ValidationStatus

# signal -> (problem_type, primary, verification, reason)
_RULES: list[tuple[frozenset[str], str, list[str], list[str], str]] = [
    (frozenset({"ode", "compartmental"}), "compartmental_ode",
     ["scipy"], ["sympy"],
     "compartmental ODE dynamics solve numerically; symbolic/theory checks verify"),
    (frozenset({"ode"}), "generic_ode",
     ["scipy"], ["sympy"],
     "time-evolution structure maps to numerical integration"),
    (frozenset({"regression", "data"}), "regression_fit",
     ["statsmodels", "scipy"], ["sympy"],
     "statistical fitting uses statsmodels/SciPy with independent symbolic checks where meaningful"),
    (frozenset({"optimization", "convex"}), "convex_optimization",
     ["cvxpy"], ["scipy"],
     "convex structure maps directly to CVXPY; SciPy can provide an independent numerical check"),
    (frozenset({"optimization"}), "generic_optimization",
     ["casadi"], ["scipy"],
     "nonlinear constrained optimization maps to CasADi with SciPy as an independent check"),
    (frozenset({"pde", "fem"}), "pde_fem",
     ["fenics"], ["sympy"],
     "PDE/FEM uses FEniCS when installed; symbolic structure can still be checked independently"),
    (frozenset({"bayesian"}), "bayesian_estimation",
     ["pymc"], ["scipy"],
     "Bayesian inference uses PyMC when available; frequentist/numerical checks remain independent"),
    (frozenset({"network"}), "network_dynamics",
     ["networkx"], ["scipy"],
     "graph structure maps to NetworkX; numerical dynamics can be cross-checked with SciPy"),
    (frozenset({"logic", "constraints"}), "constraint_verification",
     ["z3"], ["sympy", "lean"],
     "logical constraints map to Z3; symbolic or formal proof backends can verify stronger claims"),
    (frozenset({"formal", "proof"}), "formal_verification",
     ["lean"], ["z3"],
     "formal theorem checking maps to Lean with Z3 available for decidable constraint subproblems"),
    (frozenset({"control"}), "control_system",
     ["control"], ["scipy"],
     "feedback/stability analysis maps to python-control with numerical checks in SciPy"),
]

_TOOL_CLASSES = {
    "scipy": SciPyTool,
    "sympy": SymPyTool,
    "statsmodels": StatsmodelsTool,
    "cvxpy": CvxpyTool,
    "casadi": CasadiTool,
    "z3": Z3Tool,
    "lean": LeanAdapter,
}

_MODULE_TOOLS = {
    "pymc": "pymc",
    "networkx": "networkx",
    "control": "control",
    "fenics": "fenics",
}


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
    if cls is not None:
        return cls.availability().available
    module = _MODULE_TOOLS.get(name)
    return bool(module and importlib.util.find_spec(module) is not None)


def classify(problem: dict[str, Any]) -> ToolDecision:
    raw_signals = problem.get("signals", [])
    if not isinstance(raw_signals, (list, tuple, set, frozenset)):
        raise ValueError("signals must be a sequence of strings")
    signals = frozenset(str(s).lower() for s in raw_signals)
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
    chosen = [tool for tool in primary if _is_available(tool)]
    missing = [tool for tool in primary if tool not in chosen]
    verified = [tool for tool in verification if _is_available(tool)]
    verification_missing = [tool for tool in verification if tool not in verified]
    alternatives = [f"{tool}:TOOL_UNAVAILABLE" for tool in missing]
    alternatives.extend(f"{tool}:VERIFIER_UNAVAILABLE" for tool in verification_missing)

    if not chosen:
        fallback = "scipy" if _is_available("scipy") and "scipy" not in verified else None
        if fallback:
            chosen = [fallback]
            alternatives.append(f"{fallback}:degraded-fallback")
            status = ValidationStatus.WARNING
        else:
            status = ValidationStatus.TOOL_UNAVAILABLE
        return ToolDecision(problem_type, chosen, verified, reason, alternatives, status)

    status = ValidationStatus.WARNING if missing else ValidationStatus.PASS
    return ToolDecision(problem_type, chosen, verified, reason, alternatives, status)
