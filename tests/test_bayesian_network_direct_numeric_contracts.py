"""Real posterior diagnostics and graph epidemic simulation with bounded numeric claims."""

from __future__ import annotations

import math

import networkx as nx
import numpy as np
import pytest

from axiomize.bayesian.diagnostics import (
    _autocorrelation,
    effective_sample_size,
    normal_posterior_predictive,
    posterior_diagnostics,
    split_rhat,
)
from axiomize.network.epidemic import (
    _graph_size,
    _probability,
    build_er_graph,
    heterogeneity_factor,
    sir_on_network,
)


def test_constant_chain_convergence_is_explicitly_degenerate():
    c = np.ones((2, 8))
    assert split_rhat(c) == 1.0
    assert effective_sample_size(c) >= 1.0
    np.testing.assert_array_equal(_autocorrelation(c[0], 3), np.zeros(4))


def test_disagreeing_constant_chains_cannot_claim_convergence():
    c = np.array([[0.0] * 10, [5.0] * 10])
    assert math.isinf(split_rhat(c))


@pytest.mark.parametrize(
    "arr",
    [
        np.asarray([1.0, 2.0, 3.0]),
        np.ones((1, 3)),
        np.ones((2, 3)),
    ],
)
def test_insufficient_chains_and_draws_have_nonidentifiable_rhat(arr):
    assert math.isnan(split_rhat(arr))


@pytest.mark.parametrize(
    "arr",
    [
        np.asarray([1.0, 2.0]),
        np.ones((2, 3)),
    ],
)
def test_insufficient_ess_draws_are_nonidentifiable(arr):
    assert math.isnan(effective_sample_size(arr))


def test_actual_seeded_chains_have_finite_rhat_and_effective_sample_size():
    rng = np.random.default_rng(3)
    chains = rng.normal(0, 1, size=(4, 500))
    rhat = split_rhat(chains)
    ess = effective_sample_size(chains)
    assert math.isfinite(rhat)
    assert rhat < 1.1
    assert 1.0 <= ess <= chains.size


def test_posterior_diagnostics_warns_on_observed_non_convergence():
    rng = np.random.default_rng(3)
    chains = np.stack([rng.normal(i * 5, 1, size=(200, 1)) for i in range(4)])
    out = posterior_diagnostics(chains, ["mu"])
    assert out["status"] == "WARNING"
    assert out["parameters"]["mu"]["status"] == "WARNING"
    assert out["parameters"]["mu"]["r_hat"] > 1.05


def test_posterior_diagnostics_passes_on_well_mixed_chains():
    c = np.random.default_rng(7).normal(size=(4, 600, 1))
    out = posterior_diagnostics(c, ["mu"])
    assert out["status"] == "PASS", out
    assert math.isfinite(out["parameters"]["mu"]["mcse_mean"])


@pytest.mark.parametrize(
    ("data", "names"),
    [
        (np.ones((2, 5)), ["mu"]),
        (np.ones((2, 5, 2)), ["mu"]),
    ],
)
def test_posterior_shape_errors_are_refused_before_reporting_statistics(data, names):
    with pytest.raises(ValueError, match="shape"):
        posterior_diagnostics(data, names)


@pytest.mark.parametrize(
    ("means", "sigmas", "pattern"),
    [
        (np.ones((10, 3)), np.ones(10), "shape"),
        (np.ones((10, 2)), np.ones(2), "sigma vector"),
        (np.ones((9, 2)), np.ones(9), "at least 10"),
    ],
)
def test_normal_predictive_checks_require_direct_matching_draw_dimensions(means, sigmas, pattern):
    with pytest.raises(ValueError, match=pattern):
        normal_posterior_predictive(observed=np.array([1.0, 2.0]), means=means, sigmas=sigmas, seed=2)


def test_real_normal_posterior_predictive_is_seed_reproducible():
    mean = np.full((100, 3), 2.0, dtype=float)
    sd = np.ones(100)
    observation = np.array([2.0, 2.0, 2.0])
    kwargs = dict(observed=observation, means=mean, sigmas=sd, seed=42, max_replications=50)
    a = normal_posterior_predictive(**kwargs)
    b = normal_posterior_predictive(**kwargs)
    assert a == b
    assert a["replications"] == 50
    assert 0.0 <= a["coverage95"] <= 1.0
    assert 0.0 <= a["bayesian_p_values"]["mean"] <= 1.0
    assert math.isfinite(a["predictive_rmse"])


@pytest.mark.parametrize(
    ("prob", "message"),
    [
        ("invalid", "numeric"),
        (None, "numeric"),
        (-0.01, "finite and in"),
        (1.01, "finite and in"),
        (float("nan"), "finite and in"),
        (float("inf"), "finite and in"),
    ],
)
def test_direct_network_probability_contract_rejects_invalid_rates(prob, message):
    with pytest.raises(ValueError, match=message):
        _probability(prob, name="beta")


def test_network_graph_construction_is_reproducible_with_observed_seed():
    one = build_er_graph(15, 0.25, seed=9)
    two = build_er_graph(15, 0.25, seed=9)
    assert sorted(one.edges()) == sorted(two.edges())
    assert one.number_of_nodes() == 15


def test_network_graph_density_is_bounded_before_allocating_dense_edges():
    with pytest.raises(ValueError, match="expected edges"):
        build_er_graph(20_000, 1.0, seed=3)


@pytest.mark.parametrize(
    ("graph", "message"),
    [
        (object(), "NetworkX-compatible"),
        (nx.empty_graph(0), "node count"),
    ],
)
def test_direct_graph_size_refuses_unusable_network(graph, message):
    with pytest.raises(ValueError, match=message):
        _graph_size(graph)


def test_hub_heterogeneity_factor_follows_measured_degree_distribution():
    graph = nx.star_graph(5)
    deg = np.asarray([d for _, d in graph.degree()], dtype=float)
    expected = float(np.mean(deg**2) / np.mean(deg))
    assert heterogeneity_factor(graph) == pytest.approx(expected)


def test_empty_edge_graph_has_neutral_degree_heterogeneity():
    assert heterogeneity_factor(nx.empty_graph(4)) == 1.0


def test_zero_initial_infections_create_no_fabricated_epidemic():
    graph = nx.path_graph(7)
    out = sir_on_network(graph, beta=0.6, gamma=0.3, I0=0, max_steps=7, seed=3)
    assert out["peak"] == 0
    assert out["attack_rate"] == 0.0
    assert out["steps"] <= 7


def test_certain_immediate_recovery_means_attack_rate_is_only_initial_infections():
    graph = nx.complete_graph(6)
    out = sir_on_network(graph, beta=1.0, gamma=1.0, I0=2, max_steps=8, seed=4)
    assert out["attack_rate"] == pytest.approx(2 / 6)
    assert out["peak"] == 2


def test_network_epidemic_seed_reproducibility_for_true_stochastic_process():
    graph = nx.complete_graph(8)
    a = sir_on_network(graph, beta=0.35, gamma=0.15, I0=2, max_steps=15, seed=71)
    b = sir_on_network(graph, beta=0.35, gamma=0.15, I0=2, max_steps=15, seed=71)
    assert a == b
    assert 0.0 <= a["attack_rate"] <= 1.0
    assert 1.0 <= a["peak"] <= 8


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"I0": -1}, "between"),
        ({"I0": 100}, "between"),
        ({"max_steps": -1}, "between"),
        ({"max_steps": 10001}, "between"),
        ({"beta": 1.01}, "finite and in"),
        ({"gamma": -1.0}, "finite and in"),
    ],
)
def test_sir_network_parameters_enforce_true_population_and_work_bounds(kwargs, message):
    arguments = dict(beta=0.2, gamma=0.3, I0=1, max_steps=10)
    arguments.update(kwargs)
    with pytest.raises(ValueError, match=message):
        sir_on_network(nx.path_graph(5), seed=1, **arguments)
