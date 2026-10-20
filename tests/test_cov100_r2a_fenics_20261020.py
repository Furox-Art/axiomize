"""Round-2 coverage hardening for ``axiomize.tools.pde.fenics_tool``.

FEniCS/DOLFINx are optional native dependencies that are not installed in the
coverage environment. The tests below install small fake modules at the import
boundary (``sys.modules`` / the adapter's ``importlib`` handle) and then drive
the *real* adapter code, asserting the structured contract it produces and the
exact calls it makes into the backend.
"""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from axiomize.tools.base import ToolMetadata
from axiomize.tools.pde import fenics_tool
from axiomize.tools.pde.fenics_tool import FEniCSAdapter, _finite


class _Form:
    """Minimal weak-form placeholder that supports ``*`` chaining."""

    def __init__(self, tag: object) -> None:
        self.tag = tag

    def __mul__(self, other: object) -> _Form:
        return _Form((self.tag, other))

    __rmul__ = __mul__


class _DolfinxSpace:
    def __init__(self, dim: int) -> None:
        self.dim = dim


class _LegacySpace:
    def __init__(self, dimension: int) -> None:
        self._dimension = dimension

    def dim(self) -> int:
        return self._dimension


class _LegacyFunction:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def vector(self) -> SimpleNamespace:
        return SimpleNamespace(get_local=lambda: list(self._values))


def _install_fake_dolfinx(
    monkeypatch: pytest.MonkeyPatch,
    *,
    record: dict[str, Any],
    comm_size: int = 1,
    solution: list[float] | None = None,
    l2: float = 4.0,
    with_functionspace: bool = True,
) -> None:
    values = list(solution) if solution is not None else [0.0, 0.5, 1.0, 1.5, 2.0]

    mpi4py = types.ModuleType("mpi4py")
    mpi4py.MPI = SimpleNamespace(COMM_WORLD=SimpleNamespace(size=comm_size))

    petsc4py = types.ModuleType("petsc4py")
    petsc4py.PETSc = SimpleNamespace(ScalarType=float)

    ufl = types.ModuleType("ufl")
    ufl.dx = "dx"
    ufl.inner = lambda a, b: _Form(("inner", a, b))
    ufl.grad = lambda value: _Form(("grad", value))
    ufl.TrialFunction = lambda space: "u"
    ufl.TestFunction = lambda space: "v"

    def _domain(dim: int) -> SimpleNamespace:
        return SimpleNamespace(topology=SimpleNamespace(dim=dim))

    def create_unit_interval(comm: object, cells: int) -> SimpleNamespace:
        record["mesh"] = ("interval", comm, cells)
        return _domain(1)

    def create_unit_square(comm: object, cells: int, cells_y: int) -> SimpleNamespace:
        record["mesh"] = ("square", comm, cells, cells_y)
        return _domain(2)

    def locate_entities_boundary(domain: SimpleNamespace, fdim: int, marker: Any) -> Any:
        mask = marker(np.zeros((domain.topology.dim, 4)))
        record["facets"] = (fdim, mask.tolist())
        return [0, 1]

    mpi4py.__version__ = "4.0.0"
    petsc4py.__version__ = "3.21.0"
    ufl.__version__ = "2024.2.0"

    mesh = types.ModuleType("dolfinx.mesh")
    mesh.create_unit_interval = create_unit_interval
    mesh.create_unit_square = create_unit_square
    mesh.locate_entities_boundary = locate_entities_boundary

    fem = types.ModuleType("dolfinx.fem")

    def functionspace(domain: SimpleNamespace, family: tuple[str, int]) -> _DolfinxSpace:
        record["space"] = ("functionspace", family)
        return _DolfinxSpace(5)

    def function_space(domain: SimpleNamespace, family: tuple[str, int]) -> _DolfinxSpace:
        record["space"] = ("FunctionSpace", family)
        return _DolfinxSpace(5)

    if with_functionspace:
        fem.functionspace = functionspace
    fem.FunctionSpace = function_space
    fem.Function = lambda space: SimpleNamespace(x=SimpleNamespace(array=np.zeros(space.dim)))
    fem.Constant = lambda domain, value: _Form(f"source={value}")
    fem.dirichletbc = lambda g, dofs: ("bc", [float(v) for v in g.x.array], tuple(dofs))
    fem.locate_dofs_topological = lambda space, fdim, facets: [0, space.dim - 1]
    fem.form = lambda expr: expr
    fem.assemble_scalar = lambda form: l2

    class LinearProblem:
        def __init__(self, a: Any, L: Any, *, bcs: list[Any], petsc_options: dict[str, str]) -> None:
            record["problem"] = {"a": a, "L": L, "bcs": bcs, "petsc_options": petsc_options}

        def solve(self) -> SimpleNamespace:
            return SimpleNamespace(x=SimpleNamespace(array=np.asarray(values, dtype=float)))

    petsc = types.ModuleType("dolfinx.fem.petsc")
    petsc.LinearProblem = LinearProblem
    fem.petsc = petsc

    dolfinx = types.ModuleType("dolfinx")
    dolfinx.__version__ = "0.7.3"
    dolfinx.fem = fem
    dolfinx.mesh = mesh

    monkeypatch.setitem(sys.modules, "mpi4py", mpi4py)
    monkeypatch.setitem(sys.modules, "petsc4py", petsc4py)
    monkeypatch.setitem(sys.modules, "ufl", ufl)
    monkeypatch.setitem(sys.modules, "dolfinx", dolfinx)
    monkeypatch.setitem(sys.modules, "dolfinx.mesh", mesh)
    monkeypatch.setitem(sys.modules, "dolfinx.fem", fem)
    monkeypatch.setitem(sys.modules, "dolfinx.fem.petsc", petsc)


def _install_fake_legacy_fenics(
    monkeypatch: pytest.MonkeyPatch,
    *,
    record: dict[str, Any],
    values: list[float] | None = None,
) -> None:
    native = list(values) if values is not None else [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5]
    module = types.ModuleType("fenics")
    module.__version__ = "2019.2.0"

    def unit_interval(cells: int) -> SimpleNamespace:
        record["mesh"] = ("interval", cells)
        return SimpleNamespace(dim=1)

    def unit_square(cells: int, cells_y: int) -> SimpleNamespace:
        record["mesh"] = ("square", cells, cells_y)
        return SimpleNamespace(dim=2)

    module.UnitIntervalMesh = unit_interval
    module.UnitSquareMesh = unit_square
    module.FunctionSpace = lambda domain, family, degree: _LegacySpace(7)
    module.TrialFunction = lambda space: "u"
    module.TestFunction = lambda space: "v"
    module.dot = lambda a, b: _Form(("dot", a, b))
    module.grad = lambda value: _Form(("grad", value))
    module.dx = "dx"
    module.Constant = lambda value: _Form(f"const={value}")
    module.DirichletBC = lambda space, value, where: record.setdefault(
        "bc", ("DirichletBC", value.tag, where)
    )
    module.Function = lambda space: _LegacyFunction(native)
    module.solve = lambda equation, uh, bc: record.setdefault("solve", True)
    module.norm = lambda uh, kind: 1.75

    monkeypatch.setitem(sys.modules, "fenics", module)


def test_finite_helper_rejects_non_numeric_values() -> None:
    with pytest.raises(ValueError, match="source must be numeric"):
        _finite(object(), "source")
    with pytest.raises(ValueError, match="source must be finite"):
        _finite(float("nan"), "source")


def test_probe_backend_prefers_dolfinx_and_reports_version(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_importlib = SimpleNamespace(
        import_module=lambda name: SimpleNamespace(__version__="0.8.0")
    )
    monkeypatch.setattr(fenics_tool, "importlib", fake_importlib)
    assert FEniCSAdapter._probe_backend() == ("dolfinx", "0.8.0")
    assert FEniCSAdapter._probe_version() == "dolfinx-0.8.0"
    meta = FEniCSAdapter.availability()
    assert isinstance(meta, ToolMetadata)
    assert meta.available is True
    assert meta.version == "dolfinx-0.8.0"
    assert "dolfinx" in meta.reason


def test_probe_backend_falls_back_to_legacy_fenics(monkeypatch: pytest.MonkeyPatch) -> None:
    def import_module(name: str) -> SimpleNamespace:
        if name == "fenics":
            return SimpleNamespace(__version__="2019.2.0")
        raise ImportError(f"missing {name}")

    monkeypatch.setattr(fenics_tool, "importlib", SimpleNamespace(import_module=import_module))
    assert FEniCSAdapter._probe_backend() == ("fenics", "2019.2.0")
    assert FEniCSAdapter._probe_version() == "fenics-2019.2.0"
    meta = FEniCSAdapter.availability()
    assert meta.available is True
    assert meta.version == "fenics-2019.2.0"
    assert "legacy" not in meta.reason
    assert "fenics" in meta.reason


def test_probe_backend_reports_both_import_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def import_module(name: str) -> None:
        raise ImportError(f"no-{name}")

    monkeypatch.setattr(fenics_tool, "importlib", SimpleNamespace(import_module=import_module))
    with pytest.raises(RuntimeError, match="neither DOLFINx nor legacy FEniCS is runnable"):
        FEniCSAdapter._probe_backend()
    meta = FEniCSAdapter.availability()
    assert meta.available is False
    assert "no-dolfinx" in meta.reason
    assert "no-fenics" in meta.reason


def test_validate_input_refuses_non_numeric_source_and_dirichlet() -> None:
    adapter = FEniCSAdapter()
    with pytest.raises(ValueError, match="source must be numeric"):
        adapter.validate_input({"problem": "poisson", "dimension": 1, "cells": 4, "source": "abc"})
    with pytest.raises(ValueError, match="dirichlet must be numeric"):
        adapter.validate_input({"problem": "poisson", "dimension": 1, "cells": 4, "dirichlet": "abc"})
    adapter.validate_input({"problem": "poisson", "dimension": 1, "cells": 4})


@pytest.mark.parametrize(
    ("dimension", "expected_mesh"),
    [(1, ("interval", 8)), (2, ("square", 8, 8))],
)
def test_dolfinx_solver_builds_structured_poisson_problem(
    monkeypatch: pytest.MonkeyPatch,
    dimension: int,
    expected_mesh: tuple,
) -> None:
    record: dict[str, Any] = {}
    _install_fake_dolfinx(monkeypatch, record=record)
    payload = {
        "problem": "poisson", "dimension": dimension, "cells": 8,
        "source": 2.0, "dirichlet": 0.5,
    }
    result = FEniCSAdapter._solve_dolfinx(payload)
    assert result == {
        "status": "PASS",
        "backend": "dolfinx",
        "problem": "poisson",
        "dimension": dimension,
        "cells": 8,
        "degree": 1,
        "dofs": 5,
        "solution": {
            "min": 0.0, "max": 2.0, "l2": 2.0, "finite": True,
        },
    }
    mesh_record = record["mesh"]
    assert mesh_record[1] is sys.modules["mpi4py"].MPI.COMM_WORLD
    assert mesh_record[0] == expected_mesh[0]
    assert tuple(mesh_record[2:]) == expected_mesh[1:]
    assert record["facets"][0] == dimension - 1
    assert all(record["facets"][1])
    assert record["space"] == ("functionspace", ("Lagrange", 1))
    assert record["problem"]["petsc_options"] == {"ksp_type": "preonly", "pc_type": "lu"}
    assert record["problem"]["bcs"][0][0] == "bc"
    assert record["problem"]["bcs"][0][1] == [0.5] * 5
    assert record["problem"]["bcs"][0][2] == (0, 4)


def test_dolfinx_solver_uses_legacy_function_space_constructor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record: dict[str, Any] = {}
    _install_fake_dolfinx(monkeypatch, record=record, with_functionspace=False)
    result = FEniCSAdapter._solve_dolfinx({"dimension": 1, "cells": 4})
    assert result["status"] == "PASS"
    assert result["dofs"] == 5
    assert record["space"] == ("FunctionSpace", ("Lagrange", 1))


def test_dolfinx_solver_refuses_multi_rank_comm(monkeypatch: pytest.MonkeyPatch) -> None:
    record: dict[str, Any] = {}
    _install_fake_dolfinx(monkeypatch, record=record, comm_size=2)
    with pytest.raises(RuntimeError, match="single MPI rank"):
        FEniCSAdapter._solve_dolfinx({"dimension": 1, "cells": 4})
    assert "mesh" not in record


def test_dolfinx_solver_refuses_non_finite_solution(monkeypatch: pytest.MonkeyPatch) -> None:
    record: dict[str, Any] = {}
    _install_fake_dolfinx(monkeypatch, record=record, solution=[0.0, float("nan")])
    with pytest.raises(RuntimeError, match="non-finite FEM solution"):
        FEniCSAdapter._solve_dolfinx({"dimension": 1, "cells": 4})


@pytest.mark.parametrize(
    ("dimension", "expected_mesh"),
    [(1, ("interval", 6)), (2, ("square", 6, 6))],
)
def test_legacy_fenics_solver_builds_structured_poisson_problem(
    monkeypatch: pytest.MonkeyPatch,
    dimension: int,
    expected_mesh: tuple,
) -> None:
    record: dict[str, Any] = {}
    _install_fake_legacy_fenics(monkeypatch, record=record)
    result = FEniCSAdapter._solve_legacy(
        {"dimension": dimension, "cells": 6, "source": 3.0, "dirichlet": 1.5}
    )
    assert result["status"] == "PASS"
    assert result["backend"] == "fenics"
    assert result["dimension"] == dimension
    assert result["cells"] == 6
    assert result["dofs"] == 7
    assert result["solution"] == {"min": 0.0, "max": 1.5, "l2": 1.75, "finite": True}
    assert record["mesh"] == expected_mesh
    assert record["bc"] == ("DirichletBC", "const=1.5", "on_boundary")
    assert record["solve"] is True


def test_legacy_fenics_solver_refuses_non_finite_solution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record: dict[str, Any] = {}
    _install_fake_legacy_fenics(monkeypatch, record=record, values=[0.0, float("inf")])
    with pytest.raises(RuntimeError, match="non-finite FEM solution"):
        FEniCSAdapter._solve_legacy({"dimension": 1, "cells": 4})


def test_execute_dispatches_to_available_dolfinx_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record: dict[str, Any] = {}
    _install_fake_dolfinx(monkeypatch, record=record)
    adapter = FEniCSAdapter()
    result = adapter.execute({"problem": "poisson", "dimension": 1, "cells": 4})
    assert result["status"] == "PASS"
    assert result["backend"] == "dolfinx"
    assert result["dofs"] == 5
    assert record["mesh"][0] == "interval"


def test_execute_dispatches_to_legacy_backend_when_only_fenics_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record: dict[str, Any] = {}
    _install_fake_legacy_fenics(monkeypatch, record=record)
    # No dolfinx/ufl/petsc4py/mpi4py in sys.modules in this environment: the
    # adapter's real probe must select the legacy backend.
    result = FEniCSAdapter().execute({"problem": "poisson", "dimension": 2, "cells": 4})
    assert result["status"] == "PASS"
    assert result["backend"] == "fenics"
    assert record["mesh"] == ("square", 4, 4)


def test_execute_validates_before_probing_or_solving(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def boom(*args: object, **kwargs: object) -> None:
        calls.append("solver")
        raise AssertionError("solver must not run")

    monkeypatch.setattr(FEniCSAdapter, "_solve_dolfinx", staticmethod(boom))
    monkeypatch.setattr(FEniCSAdapter, "availability", classmethod(boom))
    with pytest.raises(ValueError, match="dimension must be 1 or 2"):
        FEniCSAdapter().execute({"problem": "poisson", "dimension": 3})
    assert calls == []


def test_execute_reports_unavailable_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        FEniCSAdapter, "availability", classmethod(
            lambda cls: ToolMetadata(name="fenics", available=False, reason="no native FEM")
        )
    )
    with pytest.raises(RuntimeError, match="TOOL_UNAVAILABLE: no native FEM"):
        FEniCSAdapter().execute({"problem": "poisson", "dimension": 1, "cells": 4})
