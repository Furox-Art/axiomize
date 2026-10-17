"""Direct numerical checks of advanced families, not coverage-only mocks."""

from __future__ import annotations

import numpy as np
import pytest

from axiomize.advanced_family_engine import (
    _simulate_control,
    _simulate_dae,
    _simulate_network,
    _simulate_pde,
    _solve_optimization,
)
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, VariableSpec


def model(family, *, variables, equations=(), metadata=None):
    return ModelIR(
        name="explicit-check",
        domain="physics",
        family=family,
        variables=list(variables),
        parameters=[],
        equations=list(equations),
        metadata=metadata or {},
    )


def solve(method, model_ir, *, points=5):
    return method(model_ir, t_span=(0.0, 0.5), points=points, parameter_overrides=None, seed=11)


def test_pde_neumann_constant_state_is_exactly_preserved():
    m = model(
        ModelFamily.PDE,
        variables=[VariableSpec("u", initial=3.0)],
        equations=[EquationSpec("u", "0")],
        metadata={"pde": {"grid_points": 8, "diffusion": 0.2}},
    )
    result = solve(_simulate_pde, m)
    assert result["status"] == "PASS", result
    array = np.asarray(result["states"]["u"], dtype=float)
    np.testing.assert_allclose(array, 3.0, atol=1e-8)
    assert result["solver"]["spatial_method"] == "method_of_lines"
    assert result["diagnostics"]["finite"] is True


@pytest.mark.parametrize("advection", [0.0, 0.07])
def test_pde_periodic_diffusion_conserves_spatial_mass(advection):
    m = model(
        ModelFamily.PDE,
        variables=[VariableSpec("u", initial=0.0)],
        equations=[EquationSpec("u", "0")],
        metadata={
            "pde": {
                "grid_points": 8,
                "initial_profiles": {"u": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
                "diffusion": 0.05,
                "advection": advection,
                "boundary_conditions": {"left": {"type": "periodic"}, "right": {"type": "periodic"}},
            }
        },
    )
    result = solve(_simulate_pde, m)
    assert result["status"] == "PASS", result
    arr = np.asarray(result["states"]["u"])
    np.testing.assert_allclose(arr.sum(axis=1), np.ones(arr.shape[0]), atol=2e-6)
    assert np.min(arr) >= -1e-7
    assert np.max(arr[-1]) < 1.0


def test_pde_dirichlet_boundaries_are_never_evolved_by_integrator():
    m = model(
        ModelFamily.PDE,
        variables=[VariableSpec("u", initial=0.2)],
        equations=[EquationSpec("u", "0")],
        metadata={
            "pde": {
                "grid_points": 6,
                "diffusion": 0.01,
                "boundary_conditions": {
                    "left": {"type": "dirichlet", "value": 1.0},
                    "right": {"type": "dirichlet", "value": 0.0},
                },
            }
        },
    )
    result = solve(_simulate_pde, m)
    assert result["status"] == "PASS", result
    arr = np.asarray(result["states"]["u"])
    np.testing.assert_allclose(arr[:, 0], 1.0, atol=1e-9)
    np.testing.assert_allclose(arr[:, -1], 0.0, atol=1e-9)


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"pde": "not-object"}, "metadata.pde"),
        ({"pde": {"grid_points": 4}}, "grid_points"),
        ({"pde": {"grid_points": 4100}}, "grid_points"),
        ({"pde": {"grid_points": 6, "space_span": [1, 0]}}, "space_span"),
        ({"pde": {"grid_points": 6, "space_span": [0]}}, "space_span"),
        ({"pde": {"grid_points": 6, "initial_profiles": "bad"}}, "initial_profiles"),
        ({"pde": {"grid_points": 6, "diffusion": [1, 2]}}, "diffusion"),
        ({"pde": {"grid_points": 6, "advection": [1, 2]}}, "advection"),
    ],
)
def test_pde_rejects_invalid_grid_or_coefficients(metadata, expected):
    m = model(
        ModelFamily.PDE,
        variables=[VariableSpec("u", initial=1.0)],
        equations=[EquationSpec("u", "0")],
        metadata=metadata,
    )
    with pytest.raises(ValueError, match=expected):
        solve(_simulate_pde, m)


def test_dae_index_one_algebraic_constraint_stays_satisfied():
    m = model(
        ModelFamily.DAE,
        variables=[VariableSpec("x", initial=1.0), VariableSpec("z", role="algebraic", initial=2.0)],
        equations=[EquationSpec("x", "-x"), EquationSpec("z", "2*x", kind="algebraic")],
    )
    result = solve(_simulate_dae, m)
    assert result["status"] == "PASS", result
    x = np.asarray(result["states"]["x"])
    z = np.asarray(result["states"]["z"])
    np.testing.assert_allclose(x, np.exp(-np.asarray(result["time"])), atol=5e-4)
    np.testing.assert_allclose(z, 2 * x, atol=1e-6)
    assert result["diagnostics"]["max_algebraic_residual"] < 1e-7


@pytest.mark.parametrize(
    ("vars", "equations", "expected"),
    [
        ([VariableSpec("x", initial=1.0)], [EquationSpec("x", "-x")], "both differential and algebraic"),
        ([VariableSpec("z", role="algebraic", initial=1.0)], [], "both differential and algebraic"),
        (
            [VariableSpec("x", initial=1.0), VariableSpec("z", role="algebraic")],
            [EquationSpec("x", "-x")],
            "one residual",
        ),
        (
            [VariableSpec("x"), VariableSpec("z", role="algebraic")],
            [EquationSpec("x", "-x"), EquationSpec("z", "x", kind="algebraic")],
            "finite initial",
        ),
    ],
)
def test_dae_never_invents_missing_equations_or_initial_data(vars, equations, expected):
    m = model(ModelFamily.DAE, variables=vars, equations=equations)
    with pytest.raises(ValueError, match=expected):
        solve(_simulate_dae, m)


@pytest.mark.parametrize("sense", ["minimize", "maximize"])
def test_bounded_optimization_respects_objective_sense(sense):
    if sense == "minimize":
        objective = "(x-2)**2"
        expected = 2.0
    else:
        objective = "-(x-3)**2"
        expected = 3.0
    m = model(
        ModelFamily.OPTIMIZATION,
        variables=[VariableSpec("x", role="decision", initial=1.5, bounds=(0.0, 5.0))],
        metadata={
            "optimization": {
                "objective": objective,
                "sense": sense,
                "constraints": [{"expression": "x", "relation": "between", "threshold": 1.0, "upper": 4.0}],
            }
        },
    )
    result = solve(_solve_optimization, m)
    assert result["status"] == "PASS", result
    assert result["states"]["x"] == pytest.approx(expected, abs=1e-3)
    assert result["objective"]["sense"] == sense


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"optimization": "invalid"}, "metadata.optimization"),
        ({"optimization": {}}, "requires metadata.optimization.objective"),
        ({"optimization": {"objective": "x", "constraints": "bad"}}, "constraints must be an array"),
        ({"optimization": {"objective": "x", "constraints": [5]}}, "constraint must be an object"),
        (
            {"optimization": {"objective": "x", "constraints": [{"expression": "x", "relation": "between"}]}},
            "requires upper",
        ),
        (
            {"optimization": {"objective": "x", "constraints": [{"expression": "x", "relation": "different"}]}},
            "unsupported optimization constraint",
        ),
    ],
)
def test_optimization_rejects_ambiguous_constraints(metadata, expected):
    m = model(ModelFamily.OPTIMIZATION, variables=[VariableSpec("x", role="decision", initial=1.0)], metadata=metadata)
    with pytest.raises(ValueError, match=expected):
        solve(_solve_optimization, m)


def test_stable_linear_control_follows_analytic_decay():
    m = model(
        ModelFamily.CONTROL,
        variables=[VariableSpec("x", initial=1.0, role="state")],
        metadata={"control": {"A": [[-1.0]], "B": [[0.0]], "C": [[1.0]], "D": [[0.0]], "input": 0.0}},
    )
    result = solve(_simulate_control, m)
    assert result["status"] == "PASS", result
    t = np.asarray(result["time"])
    np.testing.assert_allclose(result["states"]["x"], np.exp(-t), atol=2e-5)
    np.testing.assert_allclose(result["outputs"]["y0"], np.exp(-t), atol=2e-5)
    assert result["diagnostics"]["stability"] == "stable"


def test_feedback_control_changes_closed_loop_eigenvalue():
    m = model(
        ModelFamily.CONTROL,
        variables=[VariableSpec("x", initial=1.0, role="state")],
        metadata={
            "control": {"A": [[-1.0]], "B": [[1.0]], "C": [[1.0]], "D": [[0.0]], "feedback_gain": [1.0], "input": 0.0}
        },
    )
    result = solve(_simulate_control, m)
    assert result["status"] == "PASS", result
    assert result["solver"]["closed_loop"] is True
    assert result["diagnostics"]["eigenvalues"][0][0] == pytest.approx(-2.0)


def test_undirected_network_laplacian_conserves_total_state():
    m = model(
        ModelFamily.NETWORK,
        variables=[VariableSpec("x", initial=0.0)],
        equations=[EquationSpec("x", "laplacian_x")],
        metadata={
            "network": {
                "nodes": ["left", "right"],
                "edges": [{"source": "left", "target": "right"}],
                "initial": {"x": [1.0, 0.0]},
            }
        },
    )
    result = solve(_simulate_network, m)
    assert result["status"] == "PASS", result
    arr = np.asarray(result["states"]["x"])
    np.testing.assert_allclose(arr.sum(axis=1), 1.0, atol=1e-8)
    assert arr[-1, 0] < 1 and arr[-1, 1] > 0
    assert result["diagnostics"]["nodes"] == 2
    assert result["diagnostics"]["edges"] == 1


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"network": "invalid"}, "metadata.network"),
        ({"network": {"nodes": []}}, "non-empty"),
        ({"network": {"nodes": ["x"], "edges": [["x", "absent"]]}}, "unknown node"),
        ({"network": {"nodes": ["x"], "edges": [["x"]]}}, "source and target"),
        ({"network": {"nodes": ["x", "y"], "initial": {"x": [1]}}}, "must have length 2"),
    ],
)
def test_network_refuses_invalid_graph_and_initialization(metadata, expected):
    m = model(
        ModelFamily.NETWORK,
        variables=[VariableSpec("x", initial=1.0)],
        equations=[EquationSpec("x", "-x")],
        metadata=metadata,
    )
    with pytest.raises(ValueError, match=expected):
        solve(_simulate_network, m)
