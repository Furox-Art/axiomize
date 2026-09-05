"""Optional real FEniCS/DOLFINx finite-element executor.

The adapter intentionally exposes a small structured problem contract rather
than evaluating arbitrary UFL/Python text. It currently solves scalar Poisson
problems on unit intervals/squares with P1 Lagrange elements and constant
Dirichlet boundary conditions. The native Axiomize PDE engine remains available
when FEniCS is not installed.
"""
from __future__ import annotations

import importlib
import math
from typing import Any, ClassVar

import numpy as np

from axiomize.tools.base import ScientificTool, ToolMetadata

_MAX_CELLS_1D = 100_000
_MAX_CELLS_2D = 512


def _finite(value: Any, name: str) -> float:
    try: out=float(value)
    except (TypeError,ValueError,OverflowError) as exc: raise ValueError(f"fenics: {name} must be numeric") from exc
    if not math.isfinite(out): raise ValueError(f"fenics: {name} must be finite")
    return out


class FEniCSAdapter(ScientificTool):
    name: ClassVar[str] = "fenics"
    capabilities: ClassVar[list[str]] = ["fem", "pde_weak_form", "poisson"]

    @classmethod
    def _probe_backend(cls) -> tuple[str,str]:
        try:
            module=importlib.import_module("dolfinx")
            importlib.import_module("ufl"); importlib.import_module("petsc4py"); importlib.import_module("mpi4py")
            return "dolfinx",str(getattr(module,"__version__","unknown"))
        except Exception as first:
            try:
                module=importlib.import_module("fenics")
                return "fenics",str(getattr(module,"__version__","unknown"))
            except Exception as second:
                raise RuntimeError(f"neither DOLFINx nor legacy FEniCS is runnable: {first}; {second}") from second

    @classmethod
    def _probe_version(cls) -> str:
        backend,version=cls._probe_backend(); return f"{backend}-{version}"

    @classmethod
    def availability(cls) -> ToolMetadata:
        try:
            backend,version=cls._probe_backend()
        except Exception as exc:
            return ToolMetadata(name=cls.name,capabilities=list(cls.capabilities),available=False,reason=str(exc))
        return ToolMetadata(name=cls.name,capabilities=list(cls.capabilities),version=f"{backend}-{version}",available=True,
                            reason=f"bounded structured Poisson FEM executor via {backend}")

    def validate_input(self,payload:dict[str,Any])->None:
        if not isinstance(payload,dict): raise ValueError("fenics: payload must be an object")
        if str(payload.get("problem","poisson")).lower()!="poisson": raise ValueError("fenics: supported problem is 'poisson'")
        dimension=payload.get("dimension",1)
        if isinstance(dimension,bool) or not isinstance(dimension,(int,float)) or not float(dimension).is_integer() or int(dimension) not in {1,2}:
            raise ValueError("fenics: dimension must be 1 or 2")
        cells=payload.get("cells",32)
        if isinstance(cells,bool) or not isinstance(cells,(int,float)) or not float(cells).is_integer(): raise ValueError("fenics: cells must be an integer")
        cells=int(cells); maximum=_MAX_CELLS_1D if int(dimension)==1 else _MAX_CELLS_2D
        if not 2<=cells<=maximum: raise ValueError(f"fenics: cells must be in [2, {maximum}]")
        _finite(payload.get("source",1.0),"source"); _finite(payload.get("dirichlet",0.0),"dirichlet")
        degree=payload.get("degree",1)
        if degree!=1: raise ValueError("fenics: current bounded executor supports degree=1 only")

    def execute(self,payload:dict[str,Any])->dict[str,Any]:
        self.validate_input(payload)
        meta=self.availability()
        if not meta.available: raise RuntimeError(f"TOOL_UNAVAILABLE: {meta.reason}")
        backend,_=self._probe_backend()
        result=self._solve_dolfinx(payload) if backend=="dolfinx" else self._solve_legacy(payload)
        self.validate_output(result); return result

    @staticmethod
    def _solve_dolfinx(payload:dict[str,Any])->dict[str,Any]:
        from mpi4py import MPI
        from petsc4py import PETSc
        from dolfinx import fem,mesh
        from dolfinx.fem.petsc import LinearProblem
        import ufl
        if MPI.COMM_WORLD.size!=1: raise RuntimeError("fenics: bounded executor currently requires a single MPI rank")
        dim=int(payload.get("dimension",1)); cells=int(payload.get("cells",32)); source=_finite(payload.get("source",1.0),"source"); boundary=_finite(payload.get("dirichlet",0.0),"dirichlet")
        domain=mesh.create_unit_interval(MPI.COMM_WORLD,cells) if dim==1 else mesh.create_unit_square(MPI.COMM_WORLD,cells,cells)
        try: V=fem.functionspace(domain,("Lagrange",1))
        except AttributeError: V=fem.FunctionSpace(domain,("Lagrange",1))
        fdim=domain.topology.dim-1
        facets=mesh.locate_entities_boundary(domain,fdim,lambda x: np.full(x.shape[1],True,dtype=bool))
        dofs=fem.locate_dofs_topological(V,fdim,facets)
        g=fem.Function(V); g.x.array[:]=PETSc.ScalarType(boundary)
        bc=fem.dirichletbc(g,dofs)
        u=ufl.TrialFunction(V); v=ufl.TestFunction(V); forcing=fem.Constant(domain,PETSc.ScalarType(source))
        a=ufl.inner(ufl.grad(u),ufl.grad(v))*ufl.dx; L=forcing*v*ufl.dx
        problem=LinearProblem(a,L,bcs=[bc],petsc_options={"ksp_type":"preonly","pc_type":"lu"})
        uh=problem.solve(); values=np.asarray(uh.x.array,dtype=float)
        l2=math.sqrt(max(0.0,float(fem.assemble_scalar(fem.form(ufl.inner(uh,uh)*ufl.dx)))))
        if not np.all(np.isfinite(values)) or not math.isfinite(l2): raise RuntimeError("fenics: non-finite FEM solution")
        return {"status":"PASS","backend":"dolfinx","problem":"poisson","dimension":dim,"cells":cells,"degree":1,
                "dofs":int(values.size),"solution":{"min":float(np.min(values)),"max":float(np.max(values)),"l2":l2,"finite":True}}

    @staticmethod
    def _solve_legacy(payload:dict[str,Any])->dict[str,Any]:
        import fenics as fe  # type: ignore[import-untyped]
        dim=int(payload.get("dimension",1)); cells=int(payload.get("cells",32)); source=_finite(payload.get("source",1.0),"source"); boundary=_finite(payload.get("dirichlet",0.0),"dirichlet")
        domain=fe.UnitIntervalMesh(cells) if dim==1 else fe.UnitSquareMesh(cells,cells)
        V=fe.FunctionSpace(domain,"P",1); u=fe.TrialFunction(V); v=fe.TestFunction(V)
        a=fe.dot(fe.grad(u),fe.grad(v))*fe.dx; L=fe.Constant(source)*v*fe.dx
        bc=fe.DirichletBC(V,fe.Constant(boundary),"on_boundary"); uh=fe.Function(V); fe.solve(a==L,uh,bc)
        values=np.asarray(uh.vector().get_local(),dtype=float); l2=float(fe.norm(uh,"L2"))
        if not np.all(np.isfinite(values)) or not math.isfinite(l2): raise RuntimeError("fenics: non-finite FEM solution")
        return {"status":"PASS","backend":"fenics","problem":"poisson","dimension":dim,"cells":cells,"degree":1,
                "dofs":int(V.dim()),"solution":{"min":float(np.min(values)),"max":float(np.max(values)),"l2":l2,"finite":True}}
