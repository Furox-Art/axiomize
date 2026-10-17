"""Service-level scientific contracts and asymptotic SIR invariants."""

from __future__ import annotations

import math

import pytest

from axiomize.application.services import (
    _finite,
    _sir_asymptotic_final_size_numeric,
    _sir_asymptotic_final_size_symbolic,
    _sir_parameters,
    _xy,
    clean_data_service,
    falsify_service,
    solve_sir_service,
    uncertainty_service,
    workflow_policy_service,
)


@pytest.mark.parametrize(
    ("params", "error"),
    [
        ({"beta": -1.0}, "beta must be non-negative"),
        ({"gamma": 0.0}, "gamma must be positive"),
        ({"gamma": -1.0}, "gamma must be positive"),
        ({"N": 0.0}, "population N must be positive"),
        ({"N": -1.0}, "population N must be positive"),
        ({"I0": -1.0}, "I0 must satisfy"),
        ({"I0": 101.0, "N": 100.0}, "I0 must satisfy"),
        ({"days": 0.0}, "days must be positive"),
        ({"days": -1.0}, "days must be positive"),
        ({"days": float("inf")}, "days must be finite"),
        ({"beta": float("nan")}, "beta must be finite"),
        ({"gamma": "invalid"}, "gamma must be numeric"),
    ],
)
def test_sir_parameterization_requires_physical_bounds(params, error):
    with pytest.raises(ValueError, match=error):
        _sir_parameters(params)


@pytest.mark.parametrize(
    ("beta", "gamma", "i0", "n", "expected"),
    [
        (0.3, 0.1, 0.0, 1000.0, 0.0),
        (0.3, 0.1, 1000.0, 1000.0, 1.0),
        (0.0, 0.1, 10.0, 1000.0, 0.01),
        (0.0, 0.1, 0.0, 1000.0, 0.0),
    ],
)
def test_final_size_boundary_states_are_consistent(beta, gamma, i0, n, expected):
    actual = _sir_asymptotic_final_size_numeric(beta, gamma, i0, n)
    symbolic = _sir_asymptotic_final_size_symbolic(beta, gamma, i0, n)
    assert actual == pytest.approx(expected, abs=1e-12)
    assert symbolic == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize("r0", [0.1, 0.5, 0.9, 1.0, 1.05, 1.5, 2.0, 3.0, 5.0])
def test_sir_numeric_and_lambertw_symbolic_agree_for_finite_initial_seed(r0):
    beta = 0.2 * r0
    i0 = 10.0
    n = 10000.0
    numeric = _sir_asymptotic_final_size_numeric(beta, 0.2, i0, n)
    symbolic = _sir_asymptotic_final_size_symbolic(beta, 0.2, i0, n)
    assert i0 / n <= numeric <= 1.0
    assert numeric == pytest.approx(symbolic, abs=2e-9)
    s_inf = 1.0 - numeric
    s0 = (n - i0) / n
    assert math.log(s_inf / s0) + r0 * (1.0 - s_inf) == pytest.approx(0.0, abs=2e-9)


def test_finite_horizon_sir_is_not_confused_with_asymptotic_theory():
    out = solve_sir_service({"beta": 0.3, "gamma": 0.1, "I0": 10.0, "N": 10000.0, "days": 1.0})
    assert out["status"] == "PASS", out
    assert out["finite_horizon_converged"] is False
    assert out["numeric_theory_check"]["status"] == "INCONCLUSIVE"
    assert out["finite_horizon_final_size"] < out["asymptotic_final_size"]
    assert out["cross_validation"]["status"] == "PASS"


@pytest.mark.parametrize(
    ("t", "y", "error"),
    [
        ([0.0], [1.0], "length"),
        ([0.0, 1.0], [1.0], "length"),
        ([0.0, 1.0], [1.0, float("nan")], "finite"),
        ([float("inf"), 1.0], [1.0, 2.0], "finite"),
    ],
)
def test_service_xy_never_invents_missing_or_nonfinite_observations(t, y, error):
    with pytest.raises(ValueError, match=error):
        _xy({"t": t, "y": y})


@pytest.mark.parametrize(
    "input_payload",
    [
        {},
        {"params": {}},
        {"fit": {"params": {}}},
        {"params": {"p": [1.0, -0.5]}},
        {"params": {"p": [float("nan"), 0.1]}},
        {"params": {"p": "invalid"}},
        {"params": {"p": {"value": 1.0}}},
    ],
)
def test_uncertainty_service_does_not_fabricate_intervals(input_payload):
    out = uncertainty_service(input_payload)
    assert out["status"] == "UNVERIFIED"
    assert out["intervals"] == {}


def test_normal_interval_scale_matches_analytic_95_percent_gaussian_interval():
    out = uncertainty_service(
        {
            "params": {
                "x": [10.0, 2.0],
                "y": {"value": 4.0, "stderr": 0.0},
            }
        }
    )
    assert out["status"] == "PASS"
    assert out["uncertainty"]["n_params"] == 2
    lo, hi = out["intervals"]["x"]
    assert lo == pytest.approx(10.0 - 1.959963984540054 * 2.0, abs=1e-11)
    assert hi == pytest.approx(10.0 + 1.959963984540054 * 2.0, abs=1e-11)
    assert out["intervals"]["y"] == [4.0, 4.0]


def test_bad_data_cleaning_contract_does_not_supply_hidden_series():
    with pytest.raises(ValueError, match="requires t and y"):
        clean_data_service({"t": [1.0, 2.0]})


@pytest.mark.parametrize("policy", ["invalid", 123, []])
def test_workflow_policy_rejects_non_object_permissions(policy):
    with pytest.raises(ValueError, match="permissions must be an object"):
        workflow_policy_service({"permissions": policy})


@pytest.mark.parametrize("raw", ["invalid", {}, None])
def test_falsifier_input_contract_rejects_invalid_schema(raw):
    with pytest.raises(ValueError):
        falsify_service({"falsifiers": raw})


def test_falsifier_with_no_measured_observable_is_not_claimed_pass():
    out = falsify_service(
        {
            "falsifiers": [{"name": "min-growth", "observable": "growth", "threshold": 2.0, "direction": "above"}],
            "observations": {},
        }
    )
    assert out["model_status"] != "PASS"
    assert out["untested"]


@pytest.mark.parametrize(("value", "expected"), [(0, 0.0), ("2.5", 2.5)])
def test_numeric_conversion_is_finite(value, expected):
    assert _finite(value, name="sample") == pytest.approx(expected)


def test_all_measured_falsifiers_can_pass_without_unknown_claims():
    out = falsify_service(
        {
            "falsifiers": [
                {"name": "cap", "observable": "growth", "threshold": 2.0, "direction": "above"},
            ],
            "observations": {"growth": 1.0},
        }
    )
    assert out["model_status"] == "PASS"
    assert out["untested"] == []


def test_failed_falsification_has_priority_even_when_another_is_missing():
    out = falsify_service(
        {
            "falsifiers": [
                {"name": "cap", "observable": "growth", "threshold": 2.0, "direction": "above"},
                {"name": "unknown", "observable": "other", "threshold": 1.0, "direction": "above"},
            ],
            "observations": {"growth": 3.0},
        }
    )
    assert out["model_status"] == "FAIL"
    assert out["untested"] == ["other"]


def test_no_falsification_evidence_is_not_reported_as_a_success():
    out = falsify_service({"falsifiers": [], "observations": {}})
    assert out["model_status"] == "UNVERIFIED"
    assert out["results"] == []
