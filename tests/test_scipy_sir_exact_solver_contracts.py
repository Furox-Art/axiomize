"""Real SciPy dynamics: conservation, solver agreement, numeric safety bounds."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.tools.numerical.scipy_tool import (
    SciPyTool,
    _validate_sir_parameters,
    check_solver_agreement,
    final_size_numeric,
    solve_sir,
)


@pytest.mark.parametrize(
    ("parameter", "value", "pattern"),
    [
        ("beta", -1.0, "beta must be in"),
        ("beta", 1000001.0, "beta must be in"),
        ("gamma", -1.0, "gamma must be in"),
        ("gamma", 1000001.0, "gamma must be in"),
        ("I0", -1.0, "I0 must satisfy"),
        ("I0", 1001.0, "I0 must satisfy"),
        ("N", 0.0, "population N must be in"),
        ("N", 1e16, "population N must be in"),
        ("days", 0.0, "days must be in"),
        ("days", 1e10, "days must be in"),
        ("rtol", 0.0, "rtol must be in"),
        ("rtol", 2.0, "rtol must be in"),
        ("atol", 0.0, "atol must be in"),
        ("atol", 2.0, "atol must be in"),
        ("beta", float("nan"), "must be finite"),
        ("gamma", float("inf"), "must be finite"),
        ("N", "wrong", "must be numeric"),
    ],
)
def test_sir_solvers_refuse_unphysical_or_nonfinite_input(parameter, value, pattern):
    request = {"beta": 0.3, "gamma": 0.1, "I0": 10.0, "N": 1000.0, "days": 5.0, "rtol": 1e-8, "atol": 1e-10}
    request[parameter] = value
    with pytest.raises(ValueError, match=pattern):
        _validate_sir_parameters(**request)


@pytest.mark.parametrize("method", ["RK45", "RK23", "DOP853", "Radau", "BDF", "LSODA"])
def test_all_supported_scipy_methods_preserve_population_conservation(method):
    out = solve_sir(beta=0.3, gamma=0.1, I0=10.0, N=1000.0, days=10.0, method=method)
    assert out.success is True
    assert out.method == method
    assert out.y.shape == (3, 2000)
    assert len(out.t) == 2000
    assert out.max_conservation_error < 1e-5
    assert out.max_residual < 1e-3
    np.testing.assert_allclose(out.y.sum(axis=0), 1000.0, atol=1e-5)
    assert 0 <= out.final_size <= 1


@pytest.mark.parametrize("method", ["euler", "", 42])
def test_unknown_solver_is_rejected_not_silently_replaced(method):
    with pytest.raises(ValueError, match="method must be one of"):
        solve_sir(0.3, 0.1, 10.0, 1000.0, days=10.0, method=method)


def test_no_initial_infection_has_no_spontaneous_epidemic():
    out = solve_sir(0.3, 0.1, 0.0, 100.0, days=5.0)
    assert out.success is True
    assert out.final_size == 0.0
    np.testing.assert_allclose(out.y[1], 0.0, atol=1e-10)
    np.testing.assert_allclose(out.y[0], 100.0, atol=1e-10)


def test_zero_transmission_recovers_initial_cases_without_new_infections():
    out = solve_sir(0.0, 0.1, 10.0, 1000.0, days=10.0)
    assert out.success is True
    np.testing.assert_allclose(out.y[0], 990.0, atol=1e-6)
    assert out.final_size == pytest.approx(0.01 * (1.0 - math.exp(-1.0)), rel=1e-5)


@pytest.mark.parametrize("r0", [0.0, 0.5, 1.0])
def test_subcritical_asymptotic_final_size_theory_is_zero_for_infinitesimal_seed(r0):
    assert final_size_numeric(0.1 * r0, 0.1) == 0.0


@pytest.mark.parametrize("r0", [1.5, 2.0, 3.0])
def test_supercritical_asymptotic_size_satisfies_exact_transcendental_relation(r0):
    z = final_size_numeric(0.1 * r0, 0.1)
    assert 0 < z < 1
    assert z == pytest.approx(1.0 - math.exp(-r0 * z), abs=1e-12)


def test_final_size_theory_requires_nonzero_recovery():
    with pytest.raises(ValueError, match="gamma must be positive"):
        final_size_numeric(0.3, 0.0)


def test_actual_independent_solvers_agree_without_averaging_their_evidence():
    a = solve_sir(0.3, 0.1, 10.0, 1000.0, days=15.0, method="DOP853")
    b = solve_sir(0.3, 0.1, 10.0, 1000.0, days=15.0, method="Radau")
    accepted, diff = check_solver_agreement(a, b, tolerance=0.002)
    assert accepted is True
    assert diff < 0.002
    rejected, tight_diff = check_solver_agreement(a, b, tolerance=1e-15)
    assert tight_diff == diff
    assert rejected is (diff < 1e-15)


@pytest.mark.parametrize("tolerance", [0, -1.0, float("nan"), float("inf"), "not number"])
def test_solver_agreement_tolerance_must_be_positive_finite(tolerance):
    a = solve_sir(0.2, 0.1, 10.0, 1000.0, days=2.0)
    with pytest.raises(ValueError, match="tolerance must be"):
        check_solver_agreement(a, a, tolerance=tolerance)


def test_solver_comparison_with_nonfinite_estimate_remains_rejected():
    a = solve_sir(0.2, 0.1, 10.0, 1000.0, days=2.0)
    b = solve_sir(0.2, 0.1, 10.0, 1000.0, days=2.0)
    b.final_size = float("nan")
    accepted, diff = check_solver_agreement(a, b, tolerance=0.1)
    assert accepted is False
    assert diff == math.inf


def test_scipy_tool_dispatch_reports_real_sir_diagnostics():
    result = SciPyTool().execute({"beta": 0.2, "gamma": 0.1, "I0": 10.0, "N": 1000.0, "days": 2.0})
    assert result["success"] is True
    assert 0 <= result["final_size"] <= 1
    assert result["max_conservation_error"] < 1e-5
    assert result["max_residual"] < 1e-3


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"beta": 0.2, "gamma": 0.1},
        {"beta": 0.2, "N": 100.0},
        {"gamma": 0.1, "N": 100.0},
        {"beta": 0.2, "gamma": 0.1, "N": 100.0, "method": "wrong"},
    ],
)
def test_scipy_tool_requires_complete_validated_sir_request(payload):
    with pytest.raises(ValueError):
        SciPyTool().execute(payload)


def test_scipy_tool_unknown_action_does_not_report_success():
    with pytest.raises(ValueError, match="unknown action"):
        SciPyTool().execute({"action": "invented"})
