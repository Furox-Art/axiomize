"""Real, bounded FEniCS/FEniCSx finite-element adapter.

The adapter intentionally supports a declarative safe subset rather than
executing arbitrary Python/weak-form source.  The first supported problem is the
1D Poisson equation ``-u'' = f`` on an interval with constant source and
Dirichlet boundary values.  It uses FEniCSx (dolfinx) when available and falls
back to legacy FEniCS/dolfin.
"""
from __future__ import annotations

import importlib
import math
from typing import Any, ClassVar

import numpy as np

from axiomize.limits import MAX_RESULT_CELLS, bounded_int
from axiomize.tools.base import ScientificTool, ToolMetadata

_MAX_CELLS = min(200_000, MAX_RESULT_CELLS - 1)


def _finite(value: Any, *, name: str) -> float:
    try: out = float(value)
    except (TypeError, ValueError, OverflowError) as exc: raise ValueError(f"fenics: {name} must be numeric") from exc
    if not math.isfinite(out): raise ValueError(f"fenics: {name} must be finite")
    return out


def _backend() -> tuple[str, str] | None:
    for module, label in (("dolfinx", "dolfinx"), ("dolfin", "dolfin"), ("fenics", "fenics")):
        try:
            imported = importlib.import_module(module)
        except Exception:
            continue
        return label, str(getattr(imported, "__version__", "unknown"))
    return None


def _validated(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict): raise ValueError("fenics: payload must be an object")
    problem = str(payload.get("problem", "poisson_1d")).strip().lower()
    if problem != "poisson_1d": raise ValueError("fenics: supported problem is 'poisson_1d'")
    domain = payload.get("domain", [0.0, 1.0])
    if not isinstance(domain, (list, tuple)) or len(domain) != 2: raise ValueError("fenics: domain must be [left, right]")
    a, b = _finite(domain[0], name="domain left"), _finite(domain[1], name="domain right")
    if b <= a: raise ValueError("fenics: domain right must exceed left")
    cells = bounded_int(payload.get("cells", 64), name="fenics.cells", minimum=2, maximum=_MAX_CELLS)
    degree = bounded_int(payload.get("degree", 1), name="fenics.degree", minimum=1, maximum=2)
    source = _finite(payload.get("source", 1.0), name="source")
    bc = payload.get("dirichlet", {"left": 0.0, "right": 0.0})
    if not isinstance(bc, dict): raise ValueError("fenics: dirichlet must be an object")
    left = _finite(bc.get("left", 0.0), name="left Dirichlet value")
    right = _finite(bc.get("right", 0.0), name="right Dirichlet value")
    return {"problem": problem, "a": a, "b": b, "cells": cells, "degree": degree, "source": source, "left": left, "right": right}


def _analytic(x: np.ndarray, cfg: dict[str, Any]) -> np.ndarray:
    a, b, f, left, right = cfg["a"], cfg["b"], cfg["source"], cfg["left"], cfg["right"]
    length = b - a
    xi = x - a
    return left + (right - left) * xi / length + 0.5 * f * xi * (b - x)


def _solve_dolfinx(cfg: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, str]:
    from mpi4py import MPI  # type: ignore[import-untyped]
    from petsc4py import PETSc  # type: ignore[import-untyped]
    import ufl  # type: ignore[import-untyped]
    from dolfinx import fem, mesh  # type: ignore[import-untyped]
    from dolfinx.fem.petsc import LinearProblem  # type: ignore[import-untyped]

    domain = mesh.create_interval(MPI.COMM_SELF, cfg["cells"], [cfg["a"], cfg["b"]])
    try:
        V = fem.functionspace(domain, ("Lagrange", cfg["degree"]))
    except AttributeError:  # older FEniCSx
        V = fem.FunctionSpace(domain, ("Lagrange", cfg["degree"]))
    u, v = ufl.TrialFunction(V), ufl.TestFunction(V)
    source = fem.Constant(domain, PETSc.ScalarType(cfg["source"]))
    a_form = ufl.inner(ufl.grad(u), ufl.grad(v)) * ufl.dx
    L_form = source * v * ufl.dx

    fdim = domain.topology.dim - 1
    left_facets = mesh.locate_entities_boundary(domain, fdim, lambda x: np.isclose(x[0], cfg["a"]))
    right_facets = mesh.locate_entities_boundary(domain, fdim, lambda x: np.isclose(x[0], cfg["b"]))
    left_dofs = fem.locate_dofs_topological(V, fdim, left_facets)
    right_dofs = fem.locate_dofs_topological(V, fdim, right_facets)
    try:
        left_bc = fem.dirichletbc(PETSc.ScalarType(cfg["left"]), left_dofs, V)
        right_bc = fem.dirichletbc(PETSc.ScalarType(cfg["right"]), right_dofs, V)
    except TypeError:
        left_value = fem.Constant(domain, PETSc.ScalarType(cfg["left"]))
        right_value = fem.Constant(domain, PETSc.ScalarType(cfg["right"]))
        left_bc = fem.dirichletbc(left_value, left_dofs, V)
        right_bc = fem.dirichletbc(right_value, right_dofs, V)
    problem = LinearProblem(a_form, L_form, bcs=[left_bc, right_bc], petsc_options={"ksp_type": "preonly", "pc_type": "lu"})
    uh = problem.solve()
    x = np.asarray(V.tabulate_dof_coordinates(), dtype=float)[:, 0]
    values = np.asarray(uh.x.array, dtype=float).copy()
    order = np.argsort(x)
    return x[order], values[order], "dolfinx"


def _solve_legacy(cfg: dict[str, Any], module_name: str) -> tuple[np.ndarray, np.ndarray, str]:
    fe = importlib.import_module(module_name)
    mesh_obj = fe.IntervalMesh(cfg["cells"], cfg["a"], cfg["b"])
    V = fe.FunctionSpace(mesh_obj, "Lagrange", cfg["degree"])
    u, v = fe.TrialFunction(V), fe.TestFunction(V)
    a_form = fe.dot(fe.grad(u), fe.grad(v)) * fe.dx
    L_form = fe.Constant(cfg["source"]) * v * fe.dx
    tol = 1e-12
    left_bc = fe.DirichletBC(V, fe.Constant(cfg["left"]), lambda x, on_boundary: on_boundary and abs(x[0] - cfg["a"]) <= tol)
    right_bc = fe.DirichletBC(V, fe.Constant(cfg["right"]), lambda x, on_boundary: on_boundary and abs(x[0] - cfg["b"]) <= tol)
    uh = fe.Function(V)
    fe.solve(a_form == L_form, uh, [left_bc, right_bc])
    x = np.asarray(V.tabulate_dof_coordinates(), dtype=float).reshape(-1)
    try: values = np.asarray(uh.vector().get_local(), dtype=float)
    except AttributeError: values = np.asarray(uh.vector()[:], dtype=float)
    order = np.argsort(x)
    return x[order], values[order], module_name


class FEniCSAdapter(ScientificTool):
    name: ClassVar[str] = "fenics"
    capabilities: ClassVar[list[str]] = ["fem", "pde_weak_form", "poisson_1d"]

    @classmethod
    def _probe_version(cls) -> str:
        found = _backend()
        if found is None: raise ImportError("neither dolfinx nor legacy FEniCS/dolfin is installed")
        return f"{found[0]} {found[1]}"

    @classmethod
    def availability(cls) -> ToolMetadata:
        found = _backend()
        if found is None:
            return ToolMetadata(name=cls.name, capabilities=list(cls.capabilities), available=False,
                                reason="FEniCSx/dolfinx or legacy FEniCS/dolfin is not installed")
        return ToolMetadata(name=cls.name, capabilities=list(cls.capabilities), available=True,
                            version=found[1], reason=f"bounded declarative FEM executor via {found[0]}")

    def validate_input(self, payload: dict[str, Any]) -> None:
        _validated(payload)

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        cfg = _validated(payload)
        found = _backend()
        if found is None: raise RuntimeError("TOOL_UNAVAILABLE: FEniCSx/dolfinx or legacy FEniCS/dolfin is not installed")
        if found[0] == "dolfinx": x, values, backend = _solve_dolfinx(cfg)
        else: x, values, backend = _solve_legacy(cfg, found[0])
        if x.size > MAX_RESULT_CELLS or values.shape != x.shape or not np.all(np.isfinite(values)):
            raise RuntimeError("FEniCS backend returned malformed or non-finite solution")
        exact = _analytic(x, cfg)
        error = values - exact
        result = {
            "status": "PASS", "problem": "poisson_1d", "backend": backend,
            "x": x.tolist(), "solution": values.tolist(),
            "diagnostics": {
                "dofs": int(x.size), "cells": cfg["cells"], "degree": cfg["degree"],
                "l2_error": float(np.sqrt(np.mean(error ** 2))), "max_abs_error": float(np.max(np.abs(error))),
            },
            "equation": "-u'' = source", "boundary_conditions": {"left": cfg["left"], "right": cfg["right"]},
        }
        self.validate_output(result)
        return result
