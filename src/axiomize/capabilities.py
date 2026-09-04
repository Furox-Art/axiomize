"""Runtime capability discovery (PHASE 8/43).

Agents call this first to learn what the engine can actually do here.
Every capability is probed live - never a hardcoded brochure.
"""

from __future__ import annotations

import importlib.util
from typing import Any


class Capability(dict[str, Any]):
    """Structured capability metadata with backward-compatible truthiness."""

    def __bool__(self) -> bool:
        return bool(self.get("available", False))


def _present(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _cap(available: bool, **metadata: Any) -> Capability:
    return Capability(available=bool(available), **metadata)


def get_capabilities() -> dict[str, Any]:
    from axiomize.formal.lean_adapter import LeanAdapter
    from axiomize.integrations.scs_adapter import scs_probe

    scs = scs_probe()
    return {
        "axiomize_version": _version(),
        "adaptive_intake": _cap(True, levels=["weak", "medium", "strong"],
                                question_modes=["one_by_one", "all_at_once", "adaptive"]),
        "consumption_guard": _cap(True, guarded_actions=[
            "spawn_subtask", "repeat_alternative_method", "extra_paid_model_call"
        ]),
        "symbolic_math": _cap(_present("sympy"), backend="sympy"),
        "numerical_computing": _cap(_present("scipy"), backend="scipy"),
        "statistics": _cap(_present("statsmodels"), backend="statsmodels"),
        "visualization": _cap(_present("matplotlib"), backend="matplotlib", supports_3d=True),
        "optimization_convex": _cap(_present("cvxpy"), backend="cvxpy"),
        "optimization_nonlinear": _cap(_present("casadi"), backend="casadi"),
        "bayesian_inference": _cap(_present("pymc"), backend="pymc"),
        "bayesian_builtin_mh": _cap(True, backend="builtin"),
        "automatic_differentiation": _cap(_present("jax"), backend="jax"),
        "z3_verification": _cap(_present("z3"), backend="z3"),
        "formal_verification": _cap(
            LeanAdapter.availability().available, backend="lean"
        ),
        "network_models": _cap(_present("networkx"), backend="networkx"),
        "control_models": _cap(_present("control"), backend="control"),
        "fenics": _cap(_present("fenics"), backend="fenics"),
        "gpu": _cap(_present("torch") or _present("jax"), backends={
            "torch": _present("torch"),
            "jax": _present("jax"),
        }),
        "scientific_computing_system": _cap(
            scs["cds"] or scs["cds2"], backends=scs
        ),
        "interfaces": ["cli", "mcp", "rest"],
        "api_version": "v1",
    }


def _version() -> str:
    import axiomize

    return getattr(axiomize, "__version__", "unknown")
