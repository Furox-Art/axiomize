"""Regression tests for PDE planner/FEM adapter availability parity."""

from __future__ import annotations

from axiomize import general_engine
from axiomize import general_engine_core
from axiomize.model_ir import ModelFamily, ModelIR, SolverSpec
from axiomize.tools.base import ToolMetadata
from axiomize.tools.pde.fenics_tool import FEniCSAdapter


def _pde_model(*, solver: SolverSpec | None = None) -> ModelIR:
    return ModelIR(
        name="pde-routing",
        domain="physics",
        family=ModelFamily.PDE,
        variables=[],
        parameters=[],
        equations=[],
        solver=solver or SolverSpec(),
    )


def test_dolfinx_only_adapter_availability_selects_fem(monkeypatch) -> None:
    monkeypatch.setattr(
        FEniCSAdapter,
        "availability",
        classmethod(
            lambda cls: ToolMetadata(
                name=cls.name,
                capabilities=list(cls.capabilities),
                version="dolfinx-0.test",
                available=True,
                reason="test DOLFINx backend",
            )
        ),
    )
    model = _pde_model()

    public = general_engine.select_solver(model)
    direct_core = general_engine_core.select_solver(model)

    assert public["backend"] == "fenics"
    assert public["method"] == "finite_element"
    assert "DOLFINx" in public["reason"]
    assert direct_core == public


def test_unrunnable_legacy_module_does_not_force_fem(monkeypatch) -> None:
    monkeypatch.setattr(
        FEniCSAdapter,
        "availability",
        classmethod(
            lambda cls: ToolMetadata(
                name=cls.name,
                capabilities=list(cls.capabilities),
                available=False,
                reason="legacy module exists but backend is not runnable",
            )
        ),
    )
    # Prove that stale module-name presence cannot override the adapter probe.
    monkeypatch.setattr(general_engine_core, "_module_present", lambda name: name == "fenics")

    plan = general_engine.select_solver(_pde_model())

    assert plan["backend"] == "scipy"
    assert plan["method"] == "method_of_lines"


def test_explicit_pde_solver_configuration_is_preserved(monkeypatch) -> None:
    monkeypatch.setattr(
        FEniCSAdapter,
        "availability",
        classmethod(lambda cls: (_ for _ in ()).throw(AssertionError("probe must not run"))),
    )
    model = _pde_model(
        solver=SolverSpec(
            backend="custom",
            method="custom_method",
            fallbacks=("custom_fallback",),
        )
    )

    plan = general_engine.select_solver(model)

    assert plan == {
        "backend": "custom",
        "method": "custom_method",
        "fallbacks": ["custom_fallback"],
        "reason": "explicit solver configuration",
    }
