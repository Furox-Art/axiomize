"""Execute real bounded SciPy control/network solvers and reject malformed structure."""

from __future__ import annotations

import math

import pytest

from axiomize.advanced_family_engine import _simulate_control, _simulate_network
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, VariableSpec


def control(config=None, *, state_count=1):
    return ModelIR(
        name="control",
        domain="physics",
        family=ModelFamily.CONTROL,
        variables=[VariableSpec(f"x{i}", initial=1.0) for i in range(state_count)],
        parameters=[],
        equations=[EquationSpec("x0", "0", kind="state_space")],
        metadata={
            "control": config
            if config is not None
            else {
                "A": [[-1.0]],
                "B": [[1.0]],
                "C": [[1.0]],
                "D": [[0.0]],
                "input": 0.0,
            }
        },
    )


def network(config=None, *, has_state=True, has_equation=True):
    return ModelIR(
        name="network",
        domain="physics",
        family=ModelFamily.NETWORK,
        variables=[VariableSpec("x", initial=1.0)] if has_state else [],
        parameters=[],
        equations=[EquationSpec("x", "-x+neighbor_x_mean")] if has_equation else [],
        metadata={
            "network": config
            if config is not None
            else {
                "nodes": ["a", "b"],
                "edges": [["a", "b"]],
                "initial": {"x": [1.0, 0.0]},
            }
        },
    )


def execute(fn, m, *, points=11, t_span=(0.0, 1.0)):
    return fn(m, t_span=t_span, points=points, parameter_overrides=None, seed=5)


@pytest.mark.parametrize("initial_input", [0.0, 1.0, [0.0] * 11, {"values": [0.0, 1.0], "time": [0.0, 1.0]}])
def test_real_control_state_space_returns_time_resolved_finite_states(initial_input):
    m = control()
    m.metadata["control"]["input"] = initial_input
    out = execute(_simulate_control, m)
    assert out["status"] == "PASS", out
    assert out["solver"]["method"] == "state_space_lsim"
    assert len(out["states"]["x0"]) == 11
    assert len(out["outputs"]["y0"]) == 11
    assert all(math.isfinite(v) for v in out["states"]["x0"])


def test_feedback_gain_changes_closed_loop_eigenvalue_and_is_visible():
    m = control()
    m.metadata["control"]["feedback_gain"] = [0.5]
    out = execute(_simulate_control, m)
    assert out["status"] == "PASS"
    assert out["solver"]["closed_loop"] is True
    assert out["diagnostics"]["eigenvalues"][0][0] == pytest.approx(-1.5)


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ([], "metadata.control"),
        ({"state_space": []}, "control.state_space"),
        ({"B": [[1.0]], "C": [[1.0]], "D": [[0.0]]}, "matrix missing"),
        ({"A": [[-1.0, 0.0]], "B": [[1.0]], "C": [[1.0]], "D": [[0.0]]}, "must be square"),
        ({"A": [[-1.0]], "B": [[1.0], [1.0]], "C": [[1.0]], "D": [[0.0]]}, "dimensions are inconsistent"),
        ({"A": [[-1.0]], "B": [[1.0]], "C": [[1.0]], "D": [[0.0]], "feedback_gain": [1.0, 2.0]}, "feedback_gain shape"),
        ({"A": [[-1.0]], "B": [[1.0]], "C": [[1.0]], "D": [[0.0]], "input": [1.0, 2.0]}, "input vector shape"),
        ({"A": [[-1.0]], "B": [[1.0]], "C": [[1.0]], "D": [[0.0]], "input": [[1.0, 2.0]]}, "input must have shape"),
        (
            {"A": [[-1.0]], "B": [[1.0]], "C": [[1.0]], "D": [[0.0]], "input": {"time": [0.0, 1.0], "values": [1.0]}},
            "values/time length mismatch",
        ),
    ],
)
def test_control_solver_fails_closed_for_invalid_state_space_or_inputs(config, message):
    with pytest.raises(ValueError, match=message):
        execute(_simulate_control, control(config))


def test_control_requires_state_variable_for_each_matrix_dimension():
    with pytest.raises(ValueError, match="state variables to match A"):
        execute(_simulate_control, control(state_count=2))


def test_control_rejects_reversed_numeric_time():
    with pytest.raises(ValueError, match="t_span must be increasing"):
        execute(_simulate_control, control(), t_span=(1.0, 0.0))


def test_native_network_solver_preserves_node_coordinates_and_finite_states():
    out = execute(_simulate_network, network())
    assert out["status"] == "PASS", out
    assert out["coordinates"]["node"] == ["a", "b"]
    assert len(out["time"]) == 11
    assert len(out["states"]["x"]) == 11
    assert len(out["states"]["x"][0]) == 2
    assert out["diagnostics"]["nodes"] == 2


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ([], "metadata.network"),
        ({"nodes": []}, "non-empty array"),
        ({"nodes": ["a"], "edges": [["a"]]}, "source and target"),
        ({"nodes": ["a"], "edges": [["a", "b"]]}, "unknown node"),
        ({"nodes": ["a", "b"], "initial": []}, "network.initial"),
        ({"nodes": ["a", "b"], "initial": {"x": [1.0]}}, "must have length"),
    ],
)
def test_network_rejects_missing_topology_or_invalid_initial_conditions(config, message):
    with pytest.raises(ValueError, match=message):
        execute(_simulate_network, network(config))


def test_network_requires_a_real_state_variable():
    with pytest.raises(ValueError, match="requires state variables"):
        execute(_simulate_network, network(has_state=False))


def test_network_requires_a_real_derivative_equation():
    with pytest.raises(ValueError, match="missing derivative equations"):
        execute(_simulate_network, network(has_equation=False))


def test_network_infers_nodes_from_actual_edges_when_node_list_not_given():
    cfg = {"edges": [["a", "b"], ["b", "c"]], "initial": {"x": {"a": 1.0, "b": 0.0, "c": 0.5}}}
    out = execute(_simulate_network, network(cfg))
    assert out["status"] == "PASS", out
    assert set(out["coordinates"]["node"]) == {"a", "b", "c"}
    assert out["diagnostics"]["edges"] == 2


def test_network_uses_explicit_n_nodes_only_when_no_edge_nodes_supplied():
    cfg = {"n_nodes": 2, "initial": {"x": [0.5, 1.0]}}
    out = execute(_simulate_network, network(cfg))
    assert out["status"] == "PASS", out
    assert out["coordinates"]["node"] == ["0", "1"]


def test_network_directed_edges_preserve_directionality_metadata():
    cfg = {
        "nodes": ["a", "b"],
        "directed": True,
        "edges": [{"source": "a", "target": "b", "weight": 0.2}],
        "initial": {"x": [1.0, 0.0]},
    }
    out = execute(_simulate_network, network(cfg))
    assert out["status"] == "PASS", out
    assert out["diagnostics"]["directed"] is True
    assert out["diagnostics"]["edges"] == 1
