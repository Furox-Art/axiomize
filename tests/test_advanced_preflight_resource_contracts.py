"""Explicit resource ceilings cannot be bypassed with scientific approval."""

from __future__ import annotations

import pytest

from axiomize.general_engine import _advanced_preflight, _validated_points, _validated_span
from axiomize.limits import (
    MAX_ARRAY_ITEMS,
    MAX_BAYES_DRAWS,
    MAX_CONTROL_DIMENSION,
    MAX_DENSE_NETWORK_NODES,
    MAX_MODEL_COMPONENTS,
    MAX_OPTIMIZER_ITERATIONS,
    MAX_POINTS,
)
from axiomize.model_ir import ModelFamily, ModelIR, VariableSpec


def model(family, metadata=None):
    return ModelIR(
        name="preflight",
        domain="physics",
        family=family,
        variables=[VariableSpec("x", initial=1.0)],
        parameters=[],
        equations=[],
        metadata=metadata or {},
    )


@pytest.mark.parametrize(
    ("span", "pattern"),
    [
        ([], "must contain exactly"),
        ([0.0], "must contain exactly"),
        ("0-1", "must contain exactly"),
        ((0.0, 0.0), "strictly increasing"),
        ((1.0, 0.0), "strictly increasing"),
        ((0.0, float("nan")), "finite"),
        ((0.0, float("inf")), "finite"),
    ],
)
def test_public_numerical_span_cannot_hide_bad_horizons(span, pattern):
    with pytest.raises(ValueError, match=pattern):
        _validated_span(span)


@pytest.mark.parametrize("points", [0, 1, -1, float("inf"), MAX_POINTS + 1])
def test_public_points_must_be_bounded(points):
    with pytest.raises(ValueError, match="points"):
        _validated_points(points)


def test_point_preflight_accepts_physically_finite_bounds():
    assert _validated_span((0.0, 1.0)) == (0.0, 1.0)
    assert _validated_points(50) == 50


@pytest.mark.parametrize(
    ("cfg", "message"),
    [
        ({"nodes": []}, "dense network executor supports"),
        ({"n_nodes": 0}, "dense network executor supports"),
        ({"n_nodes": MAX_DENSE_NETWORK_NODES + 1}, "dense network executor supports"),
        ({"nodes": list(range(MAX_DENSE_NETWORK_NODES + 1))}, "dense network executor supports"),
        ({"nodes": "invalid"}, "nodes must be an array"),
        ({"edges": [["a", "b"]] * (MAX_ARRAY_ITEMS + 1)}, "network.edges exceeds"),
    ],
)
def test_network_preflight_refuses_unsafe_graph_density(cfg, message):
    with pytest.raises(ValueError, match=message):
        _advanced_preflight(model(ModelFamily.NETWORK, {"network": cfg}), points=10)


@pytest.mark.parametrize(
    "cfg",
    [
        {"nodes": ["a", "b"], "edges": [["a", "b"]]},
        {"edges": [["a", "b"]]},
        {"edges": [{"source": "a", "target": "b"}]},
        {"n_nodes": 2},
    ],
)
def test_network_preflight_counts_nodes_with_supported_explicit_shapes(cfg):
    _advanced_preflight(model(ModelFamily.NETWORK, {"network": cfg}), points=5)


@pytest.mark.parametrize(
    ("cfg", "message"),
    [
        ({"count": 0}, "agent count"),
        ({"count": -1}, "agent count"),
        ({"count": 1000001}, "agent count"),
        ({"count": "bad"}, "agent count"),
    ],
)
def test_agent_preflight_does_not_allocate_unbounded_population(cfg, message):
    with pytest.raises(ValueError, match=message):
        _advanced_preflight(model(ModelFamily.AGENT_BASED, {"agents": cfg}), points=5)


def test_agent_preflight_supports_explicit_population_size():
    _advanced_preflight(model(ModelFamily.AGENT_BASED, {"agents": {"count": 3}}), points=5)


@pytest.mark.parametrize(
    "cfg",
    [
        {"A": [[] for _ in range(MAX_CONTROL_DIMENSION + 1)]},
        {"state_space": {"A": [[] for _ in range(MAX_CONTROL_DIMENSION + 1)]}},
    ],
)
def test_control_state_dimension_is_bounded_before_any_matrix_computation(cfg):
    with pytest.raises(ValueError, match="control state dimension"):
        _advanced_preflight(model(ModelFamily.CONTROL, {"control": cfg}), points=5)


@pytest.mark.parametrize(
    ("cfg", "message"),
    [
        ({"draws": 0}, "bayesian.draws"),
        ({"draws": 49}, "bayesian.draws"),
        ({"draws": MAX_BAYES_DRAWS + 1}, "bayesian.draws"),
        ({"draws": 50, "burn": -1}, "bayesian.burn"),
        ({"draws": 50, "burn": MAX_BAYES_DRAWS + 1}, "bayesian.burn"),
        ({"draws": MAX_BAYES_DRAWS, "burn": MAX_BAYES_DRAWS, "observations": [1.0] * 25000}, "likelihood-work-unit"),
        ({"draws": 50, "observations": [1.0] * (MAX_ARRAY_ITEMS + 1)}, "bayesian observations exceed"),
    ],
)
def test_bayesian_work_units_have_hard_ceilings_even_when_approved(cfg, message):
    with pytest.raises(ValueError, match=message):
        _advanced_preflight(model(ModelFamily.BAYESIAN, {"bayesian": cfg}), points=50)


@pytest.mark.parametrize(
    ("cfg", "message"),
    [
        ({"max_events": 0}, "max_events"),
        ({"max_events": 1000001}, "max_events"),
        ({"events": [{}] * 10001}, "definitions exceed"),
    ],
)
def test_discrete_event_hard_event_count_limit(cfg, message):
    with pytest.raises(ValueError, match=message):
        _advanced_preflight(model(ModelFamily.DISCRETE_EVENT, {"discrete_event": cfg}), points=10)


@pytest.mark.parametrize(
    ("cfg", "message"),
    [
        ({"max_events_per_interval": 0}, "max_events_per_interval"),
        ({"max_events_per_interval": 10001}, "max_events_per_interval"),
        ({"events": [{}] * 1001}, "definitions exceed"),
    ],
)
def test_hybrid_preflight_rejects_unbounded_root_finding_events(cfg, message):
    with pytest.raises(ValueError, match=message):
        _advanced_preflight(model(ModelFamily.HYBRID, {"hybrid": cfg}), points=10)


@pytest.mark.parametrize(
    ("cfg", "message"),
    [
        ({"maxiter": 0}, "optimization.maxiter"),
        ({"maxiter": MAX_OPTIMIZER_ITERATIONS + 1}, "optimization.maxiter"),
        ({"constraints": [{}] * 10001}, "optimization constraints exceed"),
    ],
)
def test_optimization_preflight_refuses_unbounded_constraints(cfg, message):
    with pytest.raises(ValueError, match=message):
        _advanced_preflight(model(ModelFamily.OPTIMIZATION, {"optimization": cfg}), points=10)


@pytest.mark.parametrize(
    ("cfg", "message"),
    [
        ({"max_iterations": 0}, "multiphysics.max_iterations"),
        ({"max_iterations": 101}, "multiphysics.max_iterations"),
        ({"components": [{}] * (MAX_MODEL_COMPONENTS + 1)}, "components exceed"),
    ],
)
def test_multiphysics_preflight_limits_component_coupling_size(cfg, message):
    with pytest.raises(ValueError, match=message):
        _advanced_preflight(model(ModelFamily.MULTIPHYSICS, {"multiphysics": cfg}), points=10)


@pytest.mark.parametrize(
    ("family", "metadata"),
    [
        (ModelFamily.CONTROL, {"control": {"A": [[0.0]]}}),
        (ModelFamily.BAYESIAN, {"bayesian": {"draws": 50, "observations": [1.0, 2.0]}}),
        (ModelFamily.DISCRETE_EVENT, {"discrete_event": {"max_events": 10}}),
        (ModelFamily.HYBRID, {"hybrid": {"max_events_per_interval": 2}}),
        (ModelFamily.OPTIMIZATION, {"optimization": {"maxiter": 10}}),
        (ModelFamily.MULTIPHYSICS, {"multiphysics": {"max_iterations": 2}}),
    ],
)
def test_legal_preflight_configurations_are_not_artificially_blocked(family, metadata):
    _advanced_preflight(model(family, metadata), points=10)
