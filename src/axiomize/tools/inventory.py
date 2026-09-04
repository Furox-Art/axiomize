"""Unified live inventory of Axiomize scientific backends."""

from __future__ import annotations

import importlib.util
from importlib import metadata
from typing import Any

from axiomize.formal.lean_adapter import LeanAdapter
from axiomize.tools.logic.z3_tool import Z3Tool
from axiomize.tools.numerical.scipy_tool import SciPyTool
from axiomize.tools.optimization.casadi_tool import CasadiTool
from axiomize.tools.optimization.cvxpy_tool import CvxpyTool
from axiomize.tools.statistics.statsmodels_tool import StatsmodelsTool
from axiomize.tools.symbolic.sympy_tool import SymPyTool


def _module_tool(name: str, module: str, distribution: str,
                 capabilities: list[str]) -> dict[str, Any]:
    available = importlib.util.find_spec(module) is not None
    version = ""
    if available:
        try:
            version = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            version = "unknown"
    return {
        "available": available,
        "version": version,
        "capabilities": capabilities,
        "reason": "" if available else f"{module} not installed",
    }


def collect_tool_inventory() -> dict[str, Any]:
    tools: dict[str, Any] = {}
    for cls in (SymPyTool, SciPyTool, StatsmodelsTool, CvxpyTool, CasadiTool, Z3Tool, LeanAdapter):
        meta = cls.availability()
        tools[meta.name] = {
            "available": meta.available,
            "version": meta.version,
            "capabilities": meta.capabilities,
            "reason": meta.reason,
        }

    tools["networkx"] = _module_tool(
        "networkx", "networkx", "networkx",
        ["graphs", "network_models", "centrality", "network_dynamics"],
    )
    tools["control"] = _module_tool(
        "control", "control", "control",
        ["control_systems", "stability", "feedback", "state_space"],
    )
    tools["matplotlib"] = _module_tool(
        "matplotlib", "matplotlib", "matplotlib",
        ["plotting", "2d_visualization", "3d_visualization"],
    )
    tools["pymc"] = _module_tool(
        "pymc", "pymc", "pymc",
        ["bayesian_inference", "mcmc", "posterior_diagnostics"],
    )
    tools["jax"] = _module_tool(
        "jax", "jax", "jax",
        ["automatic_differentiation", "accelerated_numerics"],
    )
    tools["fenics"] = _module_tool(
        "fenics", "fenics", "fenics",
        ["finite_element_method", "pde"],
    )
    return {"tools": tools}
