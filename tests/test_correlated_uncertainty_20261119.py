"""Correlated uncertainty propagation from a fit covariance + honest MC accounting.

``propagate`` and the Model IR Monte-Carlo path drew independent marginals,
ignoring fit covariance. They now accept a joint covariance (fail-closed
validated) and draw correlated samples. Failed MC samples stay in the
denominator and an explicit exclusion-bias warning is reported when quantiles
are conditioned on the successful subset.
"""

from __future__ import annotations

import math

import pytest

from axiomize import advanced_diagnostics as diag
from axiomize.model_ir import ModelIR
from axiomize.uncertainty.quantify import propagate, validate_covariance_matrix


def test_covariance_drives_correlated_draws() -> None:
    # var(a+b) = 1 + 1 + 2*0.8 = 3.6 with correlation; independent would be 2.
    cov = [[1.0, 0.8], [0.8, 1.0]]
    out = propagate(lambda p: p["a"] + p["b"], {"a": (0.0, 1.0), "b": (0.0, 1.0)},
                    n=20000, seed=3, covariance=cov)
    assert out["std"] == pytest.approx(math.sqrt(3.6), abs=0.08)


def test_independent_draws_unchanged_without_covariance() -> None:
    out = propagate(lambda p: p["a"] + p["b"], {"a": (0.0, 1.0), "b": (0.0, 1.0)}, n=20000, seed=3)
    assert out["std"] == pytest.approx(math.sqrt(2.0), abs=0.08)


def test_covariance_is_parameter_order_invariant() -> None:
    cov = [[1.0, 0.8], [0.8, 1.0]]
    forward = propagate(lambda p: p["a"] + p["b"], {"a": (0.0, 1.0), "b": (0.0, 1.0)},
                        n=2000, seed=7, covariance=cov)
    reversed_order = propagate(lambda p: p["a"] + p["b"], {"b": (0.0, 1.0), "a": (0.0, 1.0)},
                               n=2000, seed=7, covariance=cov)
    assert forward == reversed_order


@pytest.mark.parametrize("cov,fragment", [
    ([[1.0]], "matrix"),
    ([[1.0, float("nan")], [float("nan"), 1.0]], "finite"),
    ([[1.0, 0.5], [0.9, 1.0]], "symmetric"),
    ([[1.0, 2.0], [2.0, 1.0]], "positive semidefinite"),
])
def test_propagate_rejects_bad_covariance(cov, fragment) -> None:
    with pytest.raises(ValueError, match=fragment):
        propagate(lambda p: p["a"], {"a": (0.0, 1.0), "b": (0.0, 1.0)}, n=10, seed=0, covariance=cov)


def test_validate_covariance_matrix_accepts_psd() -> None:
    cov = validate_covariance_matrix([[1.0, 0.5], [0.5, 1.0]], 2)
    assert cov.shape == (2, 2)


def _decay() -> ModelIR:
    return ModelIR.from_dict({
        "schema_version": "1.0", "name": "corr-decay", "domain": "physics", "family": "ode",
        "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0, "bounds": [0.0, None]}],
        "parameters": [{"name": "k", "unit": "1/day", "value": 0.5, "bounds": [0.0, 2.0]}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    })


def _two_param() -> ModelIR:
    return ModelIR.from_dict({
        "schema_version": "1.0", "name": "corr-two", "domain": "physics", "family": "ode",
        "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
        "parameters": [
            {"name": "k", "unit": "1/day", "value": 0.5, "bounds": [0.0, 2.0]},
            {"name": "c", "unit": "dimensionless", "value": 1.0},
        ],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    })


def test_joint_covariance_draws_reproducible_and_conditioned() -> None:
    kw = dict(
        model=_decay(), t_span=(0.0, 1.0), points=12, samples=6, seed=5,
        parameter_uncertainty={"k": {"distribution": "normal", "mean": 0.5, "std": 0.1}},
        parameter_covariance=[[0.01]], approve_heavy=True,
    )
    a = diag.propagate_parameter_uncertainty(**kw)
    b = diag.propagate_parameter_uncertainty(**kw)
    assert a["status"] == b["status"] == "PASS"
    assert a["states"] == b["states"]
    assert a["quantiles_conditioned_on_success"] is True
    assert "exclusion_bias_warning" not in a


def test_joint_covariance_multi_param_clips_bounds_and_fixes_others() -> None:
    out = diag.propagate_parameter_uncertainty(
        _two_param(), t_span=(0.0, 1.0), points=12, samples=8, seed=2,
        parameter_uncertainty={
            "k": {"distribution": "normal", "mean": 0.5, "std": 0.2},
            "c": {"distribution": "normal", "mean": 1.0, "std": 0.1},
        },
        parameter_covariance=[[0.04, 0.01], [0.01, 0.01]], approve_heavy=True,
    )
    assert out["status"] == "PASS"
    assert set(out["parameter_draw_summary"]) == {"k", "c"}


def test_joint_covariance_fixes_unspecified_parameter() -> None:
    out = diag.propagate_parameter_uncertainty(
        _two_param(), t_span=(0.0, 1.0), points=12, samples=6, seed=2,
        parameter_uncertainty={"k": {"distribution": "normal", "mean": 0.5, "std": 0.1}},
        parameter_covariance=[[0.01]], approve_heavy=True,
    )
    assert out["status"] == "PASS"
    assert out["parameter_draw_summary"]["c"]["std"] == 0.0


def test_exclusion_bias_warning_when_samples_fail(monkeypatch) -> None:
    real = diag.simulate_model
    call = [0]

    def intermittent(*args, **kwargs):
        call[0] += 1
        if call[0] == 2:
            return {"status": "FAIL", "stage": "isolated"}
        return real(*args, **kwargs)

    monkeypatch.setattr(diag, "simulate_model", intermittent)
    out = diag.propagate_parameter_uncertainty(
        _decay(), t_span=(0.0, 1.0), parameter_uncertainty={}, samples=3, points=12, approve_heavy=True,
    )
    assert out["status"] == "PASS"
    assert out["failed_samples"] == 1
    assert out["quantiles_conditioned_on_success"] is True
    assert "exclusion_bias_warning" in out


def test_joint_covariance_validation_error_propagates() -> None:
    with pytest.raises(ValueError, match="positive semidefinite"):
        diag.propagate_parameter_uncertainty(
            _decay(), t_span=(0.0, 1.0),
            parameter_uncertainty={"k": {"distribution": "normal", "mean": 0.5, "std": 0.1}},
            parameter_covariance=[[-1.0]], samples=3, points=12, approve_heavy=True,
        )
