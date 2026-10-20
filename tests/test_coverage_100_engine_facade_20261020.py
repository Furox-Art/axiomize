"""Coverage-completing tests for the public engine facade safeguards.

Covers request-shape validation, advanced-family resource preflight, the
structure/routing fallbacks and the numerical-refinement facade. The facade's
``numerical_refinement`` name is rebound by the v120 runtime hook, so the
originally defined function is exercised through a direct source load.
"""

from __future__ import annotations

import importlib.util

import pytest

import axiomize.general_engine as ge
from axiomize import general_engine_core as _core
from axiomize.model_ir import ModelIR


def _model(payload: dict) -> ModelIR:
    return ModelIR.from_dict({"schema_version": "1.0", "domain": "general", **payload})


def _load_facade_native():
    """Load the shipped facade, then restore core globals it patches on import."""
    names = (
        "_sympy_expression", "select_solver", "estimate_compute",
        "recommend_model_families", "export_model", "simulate_model",
    )
    saved = {name: getattr(_core, name) for name in names}
    try:
        spec = importlib.util.spec_from_file_location("axiomize_general_engine_native", ge.__file__)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, value in saved.items():
            setattr(_core, name, value)
    return module


native = _load_facade_native()


def test_validated_span_rejects_bad_shapes_and_ordering() -> None:
    with pytest.raises(ValueError, match="exactly"):
        ge._validated_span((0.0,))
    with pytest.raises(ValueError, match="finite and strictly increasing"):
        ge._validated_span((1.0, 0.0))
    assert ge._validated_span((0.0, 2.0)) == (0.0, 2.0)


def _network_model(metadata: dict) -> ModelIR:
    return _model({
        "name": "network-preflight",
        "family": "network",
        "variables": [{"name": "x", "initial": 0.5}],
        "equations": [{"target": "x", "expression": "0", "kind": "derivative"}],
        "metadata": {"network": metadata},
    })


def test_preflight_discovers_network_nodes_and_edges() -> None:
    list_edges = _network_model({"edges": [["a", "b"], ["b", "c"]]})
    assert ge._advanced_preflight(list_edges, points=5) is None
    dict_edges = _network_model({"edges": [{"source": "a", "target": "b"}]})
    assert ge._advanced_preflight(dict_edges, points=5) is None
    counts = _network_model({"edges": [], "n_nodes": 2})
    assert ge._advanced_preflight(counts, points=5) is None
    with pytest.raises(ValueError, match="network.nodes must be an array"):
        ge._advanced_preflight(_network_model({"nodes": "ab"}), points=5)
    with pytest.raises(ValueError, match="dense network executor supports"):
        ge._advanced_preflight(_network_model({"nodes": []}), points=5)
    with pytest.raises(ValueError, match="network.edges exceeds hard limit"):
        ge._advanced_preflight(
            _network_model({"edges": [["a", "b"]] * 200_001}), points=5,
        )


def test_preflight_agent_count_limit() -> None:
    model = _model({
        "name": "agent-preflight",
        "family": "agent_based",
        "variables": [{"name": "x", "initial": 1.0}],
        "equations": [{"target": "x", "expression": "x", "kind": "update"}],
        "metadata": {"agents": {"count": 0}},
    })
    with pytest.raises(ValueError, match="agent count"):
        ge._advanced_preflight(model, points=5)


def _bayesian_model(metadata: dict) -> ModelIR:
    return _model({
        "name": "bayes-preflight",
        "family": "bayesian",
        "variables": [{"name": "y", "role": "output", "initial": 1.0}],
        "parameters": [{"name": "a", "value": 1.0, "fit": True}],
        "equations": [{"target": "y", "expression": "y", "kind": "algebraic"}],
        "metadata": {"bayesian": metadata},
    })


def test_preflight_bayesian_observation_and_work_limits() -> None:
    observed_from_data = _bayesian_model({
        "outcome": "y",
        "data": {"y": [1.0, 2.0, 3.0]},
        "draws": 50,
        "burn": 0,
        "return_samples": True,
    })
    assert ge._advanced_preflight(observed_from_data, points=10) is None
    with pytest.raises(ValueError, match="observations exceed hard limit"):
        ge._advanced_preflight(
            _bayesian_model({"observations": [0.0] * 200_001}), points=10,
        )
    with pytest.raises(ValueError, match="likelihood-work-unit limit"):
        ge._advanced_preflight(
            _bayesian_model({"observations": [0.0] * 600, "draws": 100_000, "burn": 0}),
            points=10,
        )


def test_preflight_discrete_event_limits() -> None:
    base = {
        "name": "events-preflight",
        "family": "discrete_event",
        "variables": [{"name": "x", "initial": 1.0}],
        "equations": [{"target": "x", "expression": "x", "kind": "update"}],
    }
    with pytest.raises(ValueError, match="discrete-event definitions exceed hard limit"):
        ge._advanced_preflight(
            _model({**base, "metadata": {"discrete_event": [{"rate": "1", "delta": {}}] * 10_001}}),
            points=5,
        )
    with pytest.raises(ValueError, match="max_events must be between"):
        ge._advanced_preflight(
            _model({**base, "metadata": {"discrete_event": {"events": [], "max_events": 0}}}),
            points=5,
        )
    with pytest.raises(ValueError, match="max_events must be between"):
        ge._advanced_preflight(_model({**base, "metadata": {"discrete_event": 7}}), points=5)


def test_preflight_hybrid_optimization_and_multiphysics_limits() -> None:
    hybrid = _model({
        "name": "hybrid-preflight",
        "family": "hybrid",
        "variables": [{"name": "x", "initial": 1.0}],
        "equations": [{"target": "x", "expression": "0", "kind": "derivative"}],
        "metadata": {"hybrid": {"events": [{"expression": "x"}] * 1_001}},
    })
    with pytest.raises(ValueError, match="hybrid event definitions exceed hard limit"):
        ge._advanced_preflight(hybrid, points=5)

    optimization = _model({
        "name": "opt-preflight",
        "family": "optimization",
        "variables": [{"name": "x", "role": "decision", "initial": 0.0}],
        "equations": [{"target": "", "expression": "x**2", "kind": "objective"}],
        "metadata": {"optimization": {"constraints": [{"expression": "x"}] * 10_001}},
    })
    with pytest.raises(ValueError, match="optimization constraints exceed hard limit"):
        ge._advanced_preflight(optimization, points=5)

    multiphysics = _model({
        "name": "multi-preflight",
        "family": "multiphysics",
        "variables": [{"name": "y", "role": "output", "initial": 0.0}],
        "equations": [{"target": "y", "expression": "y", "kind": "algebraic"}],
        "metadata": {"multiphysics": {"components": [{"name": f"c{i}"} for i in range(65)]}},
    })
    with pytest.raises(ValueError, match="components exceed hard limit"):
        ge._advanced_preflight(multiphysics, points=5)


def test_preflight_control_dimension_limit() -> None:
    model = _model({
        "name": "control-preflight",
        "family": "control",
        "variables": [{"name": "x", "initial": 1.0}],
        "equations": [{"target": "x", "expression": "0", "kind": "state_space"}],
        "metadata": {"control": {"A": [[0.0]] * 2_049}},
    })
    with pytest.raises(ValueError, match="control state dimension exceeds hard limit"):
        ge._advanced_preflight(model, points=5)


def test_select_solver_honors_explicit_multiphysics_configuration() -> None:
    model = _model({
        "name": "multi-solver",
        "family": "multiphysics",
        "variables": [{"name": "y", "role": "output", "initial": 0.0}],
        "equations": [{"target": "y", "expression": "y", "kind": "algebraic"}],
        "solver": {"backend": "custom", "method": "custom_method"},
    })
    solver = ge.select_solver(model)
    assert solver["backend"] == "custom"
    assert solver["method"] == "custom_method"
    assert solver["reason"] == "explicit solver configuration"


def _invalid_model() -> ModelIR:
    return ModelIR(
        name="",
        domain="general",
        family=ge.ModelFamily.ODE,
        variables=[],
        parameters=[],
        equations=[],
    )


def test_simulate_once_reports_structure_failure() -> None:
    out = ge._simulate_once(_invalid_model())
    assert out["status"] == "FAIL"
    assert out["stage"] == "structure"


def test_simulate_once_routes_when_executor_is_missing(monkeypatch) -> None:
    model = _model({
        "name": "causal-route",
        "family": "causal",
        "variables": [{"name": "y", "role": "output", "initial": 0.0}],
        "equations": [{"target": "y", "expression": "y", "kind": "algebraic"}],
    })
    monkeypatch.setattr(ge, "_ADVANCED_NATIVE", ge._ADVANCED_NATIVE - {ge.ModelFamily.CAUSAL})
    out = ge._simulate_once(model, t_span=(0.0, 1.0), points=5)
    assert out["status"] == "TOOL_ROUTE_REQUIRED"
    assert out["family"] == "causal"


def test_simulate_model_marks_failed_numerical_verification(monkeypatch) -> None:
    model = _model({
        "name": "pde-verification",
        "family": "pde",
        "variables": [{"name": "u", "initial": 1.0}],
        "parameters": [{"name": "k", "value": 0.5}],
        "equations": [{"target": "u", "expression": "-k*u", "kind": "derivative"}],
        "metadata": {"pde": {"grid_points": 8}},
    })
    monkeypatch.setattr(ge, "numerical_refinement", lambda *a, **k: {"status": "FAIL"})
    out = ge.simulate_model(model, t_span=(0.0, 0.5), points=8, approve_heavy=True)
    assert out["status"] == "FAIL"
    assert out["stage"] == "numerical_verification"


def test_native_numerical_refinement_delegates_and_validates_tolerance() -> None:
    algebraic = _model({
        "name": "algebraic-refinement",
        "family": "algebraic",
        "variables": [{"name": "y", "role": "output", "initial": 1.0}],
        "equations": [{"target": "y", "expression": "y", "kind": "algebraic"}],
    })
    out = native.numerical_refinement(algebraic, t_span=(0.0, 1.0), points=5)
    assert out["status"] == "NOT_APPLICABLE"
    assert out["family"] == "algebraic"
    with pytest.raises(ValueError, match="tolerance must be finite and positive"):
        native.numerical_refinement(algebraic, t_span=(0.0, 1.0), points=5, tolerance=0.0)
