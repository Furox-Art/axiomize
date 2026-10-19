"""Real node-graph integration, weighted/directed topology and failure paths."""
from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest

from axiomize import advanced_family_engine as engine
from axiomize.model_ir import ModelIR


def graph(*, network=None, equation="c*laplacian_x", initial=1.0, variables=None):
    defaults = {
        "nodes": ["a", "b"], "edges": [["a", "b"]],
        "initial": {"x": [1.0, 0.0]},
    }
    if network is not None:
        defaults.update(network)
    return ModelIR.from_dict({
        "schema_version": "1.0", "domain": "general", "name": "weighted-graph",
        "family": "network", "variables": variables if variables is not None else [
            {"name": "x", "initial": initial, "role": "state"},
        ],
        "parameters": [{"name": "c", "value": 1.0}],
        "equations": [{"target": "x", "expression": equation, "kind": "derivative"}],
        "metadata": {"network": defaults},
    })


def simulate(model):
    return engine._simulate_network(model, t_span=(0.0, 0.5), points=7,
                                    parameter_overrides=None, seed=9)


def test_real_network_diffusion_conserves_undirected_global_mean():
    result = simulate(graph())
    assert result["status"] == "PASS"
    states = np.asarray(result["states"]["x"])
    assert states.shape == (7, 2)
    assert np.mean(states[-1]) == pytest.approx(0.5, abs=1e-7)
    assert states[-1, 0] < 1.0
    assert states[-1, 1] > 0.0
    assert result["diagnostics"]["edges"] == 1


@pytest.mark.parametrize("network,expected", [
    ({"directed": True, "edges": [["a", "b", 2.0]]}, True),
    ({"directed": False, "edges": [{"source": "a", "target": "b", "weight": 0.7}]}, False),
    ({"edges": [["a", "b", 0.0]]}, False),
])
def test_directed_or_weighted_graph_is_not_silently_replaced_by_unweighted(network,expected):
    result = simulate(graph(network=network))
    assert result["status"] == "PASS"
    assert result["diagnostics"]["directed"] is expected
    assert len(result["states"]["x"]) == len(result["time"])


def test_discovered_nodes_from_dict_edges_and_list_edges_are_reported():
    for edges in (
        [{"source": "a", "target": "b"}],
        [["a", "b"]],
    ):
        result = simulate(graph(network={"nodes": None, "edges": edges}))
        assert result["status"] == "PASS"
        assert result["coordinates"]["node"] == ["a", "b"]


def test_graph_without_explicit_topology_defaults_to_n_nodes():
    result = simulate(graph(network={"nodes": None, "edges": [], "n_nodes": 2}))
    assert result["status"] == "PASS"
    assert result["diagnostics"]["nodes"] == 2
    assert result["coordinates"]["node"] == ["0", "1"]


def test_no_neighbor_mean_falls_back_to_local_state():
    result = simulate(graph(
        equation="-x + neighbor_x_mean",
        network={"edges": [], "initial": {"x": [2.0, 3.0]}},
    ))
    assert result["status"] == "PASS"
    assert np.asarray(result["states"]["x"])[-1] == pytest.approx([2.0, 3.0])


@pytest.mark.parametrize("bad,pattern", [
    ({"nodes": []}, "non-empty array"),
    ({"nodes": "not-array"}, "non-empty array"),
    ({"edges": [["a"]]}, "source and target"),
    ({"edges": [["a", "absent"]]}, "unknown node"),
    ({"edges": [{"source": "a", "target": "unknown"}]}, "unknown node"),
    ({"initial": "not-object"}, "initial must be an object"),
    ({"initial": {"x": [1.0]}}, "must have length"),
])
def test_graph_invalid_topology_and_initial_conditions_fail_closed(bad,pattern):
    with pytest.raises(ValueError,match=pattern):
        simulate(graph(network=bad))


def test_node_keyed_initial_conditions_preserve_entity_identity():
    result = simulate(graph(network={"initial": {"x": {"a": 3.0, "b": 1.0}}}, equation="0"))
    assert result["status"] == "PASS"
    assert result["states"]["x"][0] == [3.0, 1.0]
    assert result["states"]["x"][-1] == [3.0, 1.0]


def test_missing_network_derivative_cannot_simulate_without_an_equation():
    model = graph()
    payload = model.to_dict()
    payload["equations"] = [{"target": "x", "kind": "update", "expression": "x"}]
    with pytest.raises(ValueError,match="missing derivative equations"):
        simulate(ModelIR.from_dict(payload))


def test_malformed_solver_responses_do_not_report_pass(monkeypatch):
    import scipy.integrate

    def unsuccessful(*args, **kwargs):
        return SimpleNamespace(success=False, message="no convergence", y=np.array([[1.0]]))

    monkeypatch.setattr(scipy.integrate, "solve_ivp", unsuccessful)
    result = simulate(graph())
    assert result["status"] == "FAIL"
    assert result["stage"] == "network_solve"
    assert len(result["solver_attempts"]) == 3
    assert all(row["success"] is False for row in result["solver_attempts"])


def test_nonfinite_solver_results_do_not_become_validated_trajectories(monkeypatch):
    import scipy.integrate

    def nonfinite(*args, **kwargs):
        return SimpleNamespace(success=True, message="invalid", y=np.array([[math.nan]]))

    monkeypatch.setattr(scipy.integrate, "solve_ivp", nonfinite)
    result = simulate(graph())
    assert result["status"] == "FAIL"
    assert len(result["solver_attempts"]) == 3


def test_solver_exception_is_retained_as_failure_not_discarded(monkeypatch):
    import scipy.integrate

    def refused(*args, **kwargs):
        raise RuntimeError("legitimate native solver backend failure")

    monkeypatch.setattr(scipy.integrate, "solve_ivp", refused)
    result = simulate(graph())
    assert result["status"] == "FAIL"
    assert "RuntimeError" in result["solver_attempts"][0]["message"]


def test_solver_fallback_executes_second_method_only_after_first_failure(monkeypatch):
    import scipy.integrate

    original = scipy.integrate.solve_ivp
    called = []

    def first_fails(*args, **kwargs):
        called.append(kwargs["method"])
        if kwargs["method"] == "DOP853":
            return SimpleNamespace(success=False, message="no convergence", y=np.array([[1.0]]))
        return original(*args, **kwargs)

    monkeypatch.setattr(scipy.integrate, "solve_ivp", first_fails)
    result = simulate(graph())
    assert result["status"] == "PASS"
    assert called[:2] == ["DOP853", "RK45"]
    assert result["solver"]["method"] == "RK45"
    assert len(result["solver"]["attempts"]) == 2
