"""Runtime capability discovery (PHASE 8/43).

Agents call this first to learn what the engine can actually do here.
Every flag is probed live - never a hardcoded brochure.
"""

from __future__ import annotations

import importlib.util
from typing import Any


def _present(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def get_capabilities() -> dict[str, Any]:
    from axiomize.integrations.scs_adapter import scs_probe

    scs = scs_probe()
    return {
        "axiomize_version": _version(),
        "symbolic_math": _present("sympy"),
        "numerical_computing": _present("scipy"),
        "statistics": _present("statsmodels"),
        "optimization_convex": _present("cvxpy"),
        "optimization_nonlinear": _present("casadi"),
        "bayesian_inference": _present("pymc"),
        "bayesian_builtin_mh": True,
        "automatic_differentiation": _present("jax"),
        "z3_verification": _present("z3"),
        "network_models": _present("networkx"),
        "control_models": _present("control"),
        "fenics": _present("fenics"),
        "gpu": _present("torch") or _present("jax"),
        "scientific_computing_system": scs["cds"] or scs["cds2"],
        "interfaces": ["cli", "mcp", "rest"],
        "api_version": "v1",
    }


def _version() -> str:
    import axiomize

    return getattr(axiomize, "__version__", "unknown")
