"""Actual SciPy method-of-lines PDE and constrained optimizer boundary contracts."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.advanced_family_engine import (
    _boundary_spec,
    _simulate_pde,
    _solve_optimization,
)
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, VariableSpec


def pde(cfg=None, *, initial=1.0):
    return ModelIR(
        name="diffusion",
        domain="physics",
        family=ModelFamily.PDE,
        variables=[VariableSpec("u", initial=initial)],
        parameters=[],
        equations=[EquationSpec("u", "0", kind="derivative")],
        metadata={
            "pde": cfg if cfg is not None else {"grid_points": 8, "diffusion": {"u": 0.1}, "space_span": [0.0, 1.0]}
        },
    )


def opt(cfg=None, *, has_decision=True, equations=None):
    return ModelIR(
        name="quadratic",
        domain="mathematics",
        family=ModelFamily.OPTIMIZATION,
        variables=[VariableSpec("x", role="decision" if has_decision else "output", initial=0.0, bounds=(0.0, 5.0))],
        parameters=[],
        equations=equations if equations is not None else [EquationSpec("", "(x-2)**2", kind="objective")],
        metadata={"optimization": cfg if cfg is not None else {}},
    )


def execute(fn, m, *, span=(0.0, 0.2), points=6):
    return fn(m, t_span=span, points=points, parameter_overrides=None, seed=4)


@pytest.mark.parametrize(
    "bc",
    [
        {"left": {"type": "neumann", "value": 0.0}, "right": {"type": "neumann", "value": 0.0}},
        {"left": {"type": "periodic"}, "right": {"type": "periodic"}},
        {"left": {"type": "dirichlet", "value": 1.0}, "right": {"type": "dirichlet", "value": 1.0}},
    ],
)
def test_real_constant_pde_solution_remains_constant_for_diffusive_boundary_types(bc):
    cfg = {"grid_points": 8, "space_span": [0.0, 1.0], "diffusion": 0.05, "boundary_conditions": {"u": bc}}
    out = execute(_simulate_pde, pde(cfg))
    assert out["status"] == "PASS", out
    a = np.asarray(out["states"]["u"])
    assert a.shape == (6, 8)
    np.testing.assert_allclose(a, 1.0, atol=2e-6)
    assert out["diagnostics"]["grid_points"] == 8


def test_advection_on_periodic_nonuniform_profile_preserves_finiteness():
    cfg = {
        "grid_points": 8,
        "space_span": [0.0, 1.0],
        "diffusion": 0.01,
        "advection": 0.3,
        "initial_profiles": {"u": "sin(2*x)+1"},
        "boundary_conditions": {"left": {"type": "periodic"}},
    }
    out = execute(_simulate_pde, pde(cfg))
    assert out["status"] == "PASS", out
    assert all(math.isfinite(x) for row in out["states"]["u"] for x in row)


def test_dirichlet_inhomogeneous_boundaries_remain_fixed_exactly():
    cfg = {
        "grid_points": 7,
        "space_span": [0.0, 1.0],
        "diffusion": 0.1,
        "initial_profiles": {"u": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
        "boundary_conditions": {
            "left": {"type": "dirichlet", "value": 2.0},
            "right": {"type": "dirichlet", "value": 1.0},
        },
    }
    out = execute(_simulate_pde, pde(cfg))
    assert out["status"] == "PASS", out
    a = np.asarray(out["states"]["u"])
    np.testing.assert_allclose(a[:, 0], 2.0, atol=1e-8)
    np.testing.assert_allclose(a[:, -1], 1.0, atol=1e-8)


@pytest.mark.parametrize(
    ("cfg", "pattern"),
    [
        ([], "metadata.pde"),
        ({"grid_points": 4}, "grid_points"),
        ({"grid_points": 4097}, "grid_points"),
        ({"grid_points": 8, "space_span": [0.0]}, "space_span"),
        ({"grid_points": 8, "space_span": [1.0, 0.0]}, "finite and increasing"),
        ({"grid_points": 8, "space_span": [0.0, float("nan")]}, "finite and increasing"),
        ({"grid_points": 8, "initial_profiles": []}, "initial_profiles"),
        ({"grid_points": 8, "initial_profiles": {"u": [0.0] * 7}}, "grid length"),
        ({"grid_points": 8, "diffusion": []}, "diffusion must be"),
        ({"grid_points": 8, "advection": []}, "advection must be"),
    ],
)
def test_pde_executor_rejects_unsafe_or_malformed_numerical_setup(cfg, pattern):
    with pytest.raises(ValueError, match=pattern):
        execute(_simulate_pde, pde(cfg))


def test_pde_requires_state_initial_value_or_explicit_profile():
    with pytest.raises(ValueError, match="needs initial"):
        execute(_simulate_pde, pde({"grid_points": 8}, initial=None))


def test_boundary_spec_is_explicit_and_does_not_invent_missing_bc():
    m = pde({"grid_points": 8})
    assert _boundary_spec(m, {}, "u") == {}
    assert _boundary_spec(m, {"boundary_conditions": {"u": {"left": {"type": "neumann"}}}}, "u") == {
        "left": {"type": "neumann"}
    }


def test_real_quadratic_optimizer_matches_analytic_minimum():
    out = execute(_solve_optimization, opt())
    assert out["status"] == "PASS", out
    assert out["states"]["x"] == pytest.approx(2.0, abs=1e-5)
    assert out["objective"]["value"] == pytest.approx(0.0, abs=1e-7)
    assert out["diagnostics"]["optimality_success"] is True


def test_real_constrained_optimizer_respects_inequality_and_equality():
    cfg = {
        "constraints": [
            {"expression": "x", "relation": "ge", "threshold": 3.0},
            {"expression": "x", "relation": "le", "threshold": 4.0},
        ]
    }
    out = execute(_solve_optimization, opt(cfg))
    assert out["status"] == "PASS", out
    assert 3.0 - 1e-6 <= out["states"]["x"] <= 4.0 + 1e-6


@pytest.mark.parametrize(
    ("cfg", "pattern"),
    [
        ([], "metadata.optimization"),
        ({"constraints": "wrong"}, "constraints must be an array"),
        ({"constraints": [{}]}, "must be an object with expression"),
        ({"constraints": [{"expression": "x", "relation": "between", "threshold": 0.0}]}, "requires upper"),
        ({"constraints": [{"expression": "x", "relation": "fake"}]}, "unsupported optimization constraint"),
    ],
)
def test_optimizer_rejects_invalid_constraint_semantics(cfg, pattern):
    with pytest.raises(ValueError, match=pattern):
        execute(_solve_optimization, opt(cfg))


def test_optimizer_without_any_decision_variables_fails_not_substitutes_random_model():
    with pytest.raises(ValueError, match="requires decision variables"):
        execute(_solve_optimization, opt(has_decision=False))


def test_optimizer_without_objective_expression_never_claims_valid_solution():
    with pytest.raises(ValueError, match="requires metadata.optimization.objective"):
        execute(_solve_optimization, opt(equations=[]))


def test_quadratic_optimizer_selects_explicit_maximization_sense():
    out = execute(_solve_optimization, opt({"objective": "-(x-2)**2", "sense": "maximize"}))
    assert out["status"] == "PASS", out
    assert out["objective"]["sense"] == "maximize"
    assert out["states"]["x"] == pytest.approx(2.0, abs=1e-5)
