"""Round-2 coverage hardening: Bayesian MH, network epidemic, SCS, verification v2."""

from __future__ import annotations

import math
import sys
import types
from types import SimpleNamespace

import networkx as nx
import numpy as np
import pytest

from axiomize import numerical_verification_v2 as verification
from axiomize.bayesian import engine_v2
from axiomize.integrations import scs_adapter
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, ParameterSpec, VariableSpec
from axiomize.network import epidemic
from axiomize.tools.numerical import scipy_tool
from axiomize.validation.status import ValidationStatus

# ---------------------------------------------------------------------------
# Bayesian engine 2.0
# ---------------------------------------------------------------------------


def _bayes_model(*, parameters, proposal_scale=None, equation_expression="a + y") -> ModelIR:
    cfg = {
        "data": {"y": [0.0, 0.0]},
        "observations": [1.0, 2.0],
        "draws": 50,
        "burn": 0,
        "chains": 2,
        "sigma": 0.5,
    }
    if proposal_scale is not None:
        cfg["proposal_scale"] = proposal_scale
    return ModelIR(
        name="bayes-probe",
        domain="test",
        family=ModelFamily.BAYESIAN,
        variables=[VariableSpec(name="x", unit="dimensionless", initial=0.0)],
        parameters=parameters,
        equations=[EquationSpec(target="", expression=equation_expression, kind="likelihood")],
        independent_variable="t",
        independent_unit="day",
        metadata={"bayesian": cfg},
    )


def test_log_prior_bounds_reject_values_outside_the_support() -> None:
    assert engine_v2._log_prior(-0.1, None, (0.0, 1.0), 0.5) == -math.inf
    assert engine_v2._log_prior(1.1, None, (0.0, 1.0), 0.5) == -math.inf


def test_log_prior_without_prior_uses_a_finite_bounded_center_fallback() -> None:
    value = engine_v2._log_prior(0.5, None, (0.0, 1.0), 0.5)
    assert math.isfinite(value)
    assert value == pytest.approx(-math.log(10.0))


def test_inference_uses_likelihood_equation_when_mean_expression_is_absent() -> None:
    model = _bayes_model(parameters=[ParameterSpec(name="a", value=1.0, fit=True)])
    result = engine_v2.infer_bayesian_model(
        model, t_span=(0.0, 1.0), points=50, parameter_overrides=None, seed=3
    )
    assert result["status"] == "PASS"
    assert set(result["posterior"]) == {"a"}
    assert result["diagnostics"]["chains"] == 2
    assert result["diagnostics"]["finite"] is True


def test_proposal_scale_uses_prior_sigma_bounds_and_center_fallback() -> None:
    model = _bayes_model(
        parameters=[
            ParameterSpec(
                name="a",
                value=1.0,
                fit=True,
                prior={"dist": "normal", "sigma": 0.5},
            ),
            ParameterSpec(name="b", value=0.5, fit=True, bounds=(0.0, 1.0)),
            ParameterSpec(name="c", value=2.0, fit=True),
        ],
        equation_expression="a + b + c + y",
    )
    result = engine_v2.infer_bayesian_model(
        model, t_span=(0.0, 1.0), points=50, parameter_overrides=None, seed=7
    )
    assert result["status"] == "PASS"
    assert set(result["posterior"]) == {"a", "b", "c"}
    assert all(0.0 <= rate <= 1.0 for rate in result["diagnostics"]["acceptance_rate_by_chain"])


def test_scalar_proposal_scale_is_applied_to_every_parameter() -> None:
    model = _bayes_model(
        parameters=[ParameterSpec(name="a", value=1.0, fit=True)],
        proposal_scale=0.05,
    )
    result = engine_v2.infer_bayesian_model(
        model, t_span=(0.0, 1.0), points=50, parameter_overrides=None, seed=11
    )
    assert result["status"] == "PASS"
    assert result["posterior"]["a"]["sd"] >= 0.0
    assert result["diagnostics"]["finite"] is True


# ---------------------------------------------------------------------------
# Network epidemic dynamics
# ---------------------------------------------------------------------------


def test_probability_rejects_non_numeric_values() -> None:
    with pytest.raises(ValueError, match="beta must be numeric"):
        epidemic._probability(object(), name="beta")


@pytest.mark.parametrize("value", [2.0, -0.1, float("nan"), float("inf")])
def test_probability_rejects_values_outside_the_unit_interval(value) -> None:
    with pytest.raises(ValueError, match="beta must be finite and in \\[0, 1\\]"):
        epidemic._probability(value, name="beta")


def test_build_er_graph_rejects_dense_expected_work_before_allocation() -> None:
    with pytest.raises(ValueError, match="expected edges, exceeding hard limit"):
        epidemic.build_er_graph(20_000, 1.0)


def test_graph_size_wraps_unreadable_graph_errors() -> None:
    class _BrokenGraph:
        def number_of_nodes(self) -> int:
            raise RuntimeError("broken graph")

    with pytest.raises(ValueError, match="NetworkX-compatible graph: broken graph"):
        epidemic._graph_size(_BrokenGraph())


def test_graph_size_rejects_empty_graphs() -> None:
    with pytest.raises(ValueError, match="node count must be in 1"):
        epidemic._graph_size(nx.Graph())


def test_graph_size_rejects_edge_counts_over_the_limit(monkeypatch) -> None:
    monkeypatch.setattr(epidemic, "MAX_NETWORK_EDGES", 1)
    with pytest.raises(ValueError, match="edge count must be in 0..1"):
        epidemic._graph_size(nx.path_graph(3))


def test_heterogeneity_factor_rejects_non_finite_degrees(monkeypatch) -> None:
    monkeypatch.setattr(epidemic.np, "fromiter", lambda *args, **kwargs: np.array([1e308]))
    with np.errstate(over="ignore"), pytest.raises(
        RuntimeError, match="heterogeneity factor is non-finite"
    ):
        epidemic.heterogeneity_factor(nx.path_graph(1))


def test_sir_on_network_rejects_excessive_worst_case_work(monkeypatch) -> None:
    monkeypatch.setattr(epidemic, "MAX_RESULT_CELLS", 10)
    with pytest.raises(ValueError, match="worst-case work"):
        epidemic.sir_on_network(nx.path_graph(5), beta=0.1, gamma=0.2, I0=0, max_steps=365)


# ---------------------------------------------------------------------------
# SCS adapter
# ---------------------------------------------------------------------------


def _install_fake_cds(monkeypatch, solver) -> None:
    cds = types.ModuleType("cds")
    diffeq = types.ModuleType("cds.diffeq")
    diffeq.solve_system = solver
    cds.diffeq = diffeq
    monkeypatch.setitem(sys.modules, "cds", cds)
    monkeypatch.setitem(sys.modules, "cds.diffeq", diffeq)


def test_solve_sir_cds_uses_the_optional_backend_contract(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_solve_system(rhs, t0, y0, days, dt):
        captured["args"] = (t0, y0, days, dt)
        captured["derivative"] = rhs(t0, y0)
        return [t0, days], [[900.0, 100.0, 0.0], [200.0, 100.0, 700.0]]

    _install_fake_cds(monkeypatch, fake_solve_system)
    result = scs_adapter.solve_sir_cds(0.3, 0.1, 100.0, 1000.0, days=30.0, dt=0.1)
    assert result["t"] == [0.0, 30.0]
    assert result["final_size"] == pytest.approx(0.7)
    assert captured["args"] == (0.0, [900.0, 100.0, 0.0], 30.0, 0.1)
    assert captured["derivative"] == pytest.approx([-27.0, 17.0, 10.0])


def test_cross_validate_sir_reports_unavailable_without_the_backend(monkeypatch) -> None:
    monkeypatch.setattr(scs_adapter, "scs_probe", lambda: {"cds": False, "cds2": False})
    result = scs_adapter.cross_validate_sir(0.3, 0.1, 10.0, 1000.0)
    assert result.status == ValidationStatus.TOOL_UNAVAILABLE
    assert result.primary_result is None
    assert result.recommended_action


def test_cross_validate_sir_compares_primary_and_verification_values(monkeypatch) -> None:
    monkeypatch.setattr(scs_adapter, "scs_probe", lambda: {"cds": True, "cds2": False})
    monkeypatch.setattr(scs_adapter, "solve_sir_cds", lambda *args, **kwargs: {"final_size": 0.42})
    monkeypatch.setattr(
        scipy_tool, "solve_sir", lambda *args, **kwargs: SimpleNamespace(final_size=0.42)
    )
    result = scs_adapter.cross_validate_sir(0.3, 0.1, 10.0, 1000.0, tolerance=1e-6)
    assert result.status == ValidationStatus.PASS
    assert result.difference == pytest.approx(0.0)
    assert result.primary_result == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# Numerical verification v2
# ---------------------------------------------------------------------------


def test_relative_rejects_incompatible_or_non_finite_arrays() -> None:
    with pytest.raises(ValueError, match="incompatible/non-finite"):
        verification._relative(np.zeros(2), np.zeros(3))
    with pytest.raises(ValueError, match="incompatible/non-finite"):
        verification._relative(np.array([math.inf]), np.array([1.0]))


def test_resolution_study_falls_back_to_numeric_summaries_without_states() -> None:
    model = SimpleNamespace(family=ModelFamily.CONTROL)

    def simulate_once(model, *, t_span, points, parameter_overrides, seed, approve_heavy):
        assert approve_heavy is True
        return {"status": "PASS", "states": {}, "score": float(points)}

    result = verification.numerical_refinement_study_v2(
        model,
        simulate_once=simulate_once,
        t_span=(0.0, 1.0),
        points=2,
        approve_heavy=True,
        tolerance=1e-3,
    )
    assert result["study"] == "output_resolution_refinement"
    assert result["error_metric"] == "numeric-summary relative difference"
    assert result["estimated_numerical_error"] == pytest.approx(1.0 / 3.0)
    assert result["converged"] is False
    assert result["levels"] == [2, 3]
