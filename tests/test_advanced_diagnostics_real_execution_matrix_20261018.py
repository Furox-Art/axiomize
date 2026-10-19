"""Auditable uncertainty propagation and local stability scans on native ODEs."""

from __future__ import annotations

import math

import pytest

from axiomize import advanced_diagnostics as diag
from axiomize.model_ir import ModelIR


def _decay_model():
    return ModelIR.from_dict({
        "schema_version": "1.0", "domain": "physics", "name": "bounded-decay", "family": "ode",
        "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0, "bounds": [0.0, None]}],
        "parameters": [{"name": "k", "unit": "1/day", "value": 0.5, "bounds": [0.0, 2.0]}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
        "constraints": [], "assumptions": ["first-order ODE"],
    })


def test_real_ode_uncertainty_requires_explicit_heavy_approval():
    out = diag.propagate_parameter_uncertainty(
        _decay_model(), t_span=(0.0, 1.0), parameter_uncertainty={},
        samples=3, points=12,
    )
    assert out["status"] == "APPROVAL_REQUIRED"
    assert "cost" in out


@pytest.mark.parametrize("samples", [0, 1, -1, 100001])
def test_requested_sample_counts_stay_within_hard_limits(samples):
    with pytest.raises(ValueError, match="samples"):
        diag.propagate_parameter_uncertainty(
            _decay_model(), t_span=(0.0, 1.0), parameter_uncertainty={},
            samples=samples,
        )


@pytest.mark.parametrize("quantiles", [(), (-0.1,), (1.1,), ((0.2, 0.5),)])
def test_quantile_grid_refuses_non_probabilities(quantiles):
    with pytest.raises(ValueError, match="quantiles"):
        diag.propagate_parameter_uncertainty(
            _decay_model(), t_span=(0.0, 1.0), parameter_uncertainty={},
            quantiles=quantiles,
        )


def test_unrecognized_parameter_does_not_enter_model_simulation():
    with pytest.raises(ValueError, match="unknown parameters"):
        diag.propagate_parameter_uncertainty(
            _decay_model(), t_span=(0.0, 1.0),
            parameter_uncertainty={"not_existing": {"distribution": "fixed", "value": 1}},
            samples=2, points=12, approve_heavy=True,
        )


def test_actual_native_ode_uncertainty_draws_are_reproducible():
    kw = dict(
        model=_decay_model(), t_span=(0.0, 1.0), points=18, samples=4, seed=11,
        parameter_uncertainty={"k": {"distribution": "fixed", "value": 0.5}},
        quantiles=(0.1, 0.5, 0.9), approve_heavy=True,
    )
    a = diag.propagate_parameter_uncertainty(**kw)
    b = diag.propagate_parameter_uncertainty(**kw)
    assert a["status"] == b["status"] == "PASS"
    assert (a["successful_samples"], a["failed_samples"]) == (4, 0)
    assert a["states"] == b["states"]
    assert a["parameter_draw_summary"] == b["parameter_draw_summary"]
    assert len(a["states"]["x"]["mean"]) == 18
    assert abs(a["states"]["x"]["mean"][-1] - math.exp(-0.5)) < 1e-3
    assert all(v == 0.0 for v in a["states"]["x"]["std"])


def test_all_failed_parameter_draws_cannot_be_reported_as_pass(monkeypatch):
    monkeypatch.setattr(diag, "simulate_model", lambda *args, **kw: {"status": "FAIL", "stage": "native-integrity"})
    out = diag.propagate_parameter_uncertainty(
        _decay_model(), t_span=(0.0, 1.0), parameter_uncertainty={},
        points=12, samples=3, approve_heavy=True,
    )
    assert out["status"] == "FAIL"
    assert out["successful_samples"] == 0
    assert out["failed_samples"] == 3
    assert len(out["failures"]) == 3


def test_partial_failed_draws_remain_in_denominator(monkeypatch):
    real = diag.simulate_model
    call = [0]
    def intermittent(*args, **kwargs):
        call[0] += 1
        if call[0] == 2:
            return {"status": "FAIL", "stage": "isolated-solver-failure"}
        return real(*args, **kwargs)
    monkeypatch.setattr(diag, "simulate_model", intermittent)
    out = diag.propagate_parameter_uncertainty(
        _decay_model(), t_span=(0.0, 1.0), parameter_uncertainty={},
        samples=3, points=12, approve_heavy=True,
    )
    assert out["status"] == "PASS"
    assert out["successful_samples"] == 2
    assert out["failed_samples"] == 1
    assert out["success_fraction"] == pytest.approx(2 / 3)
    assert out["failures"][0]["sample"] == 1


def test_local_bifurcation_scan_requires_multiple_parameter_values():
    with pytest.raises(ValueError, match="at least two"):
        diag.bifurcation_scan(_decay_model(), parameter="k", values=[0.1])


def test_local_bifurcation_scan_requires_approval():
    out = diag.bifurcation_scan(_decay_model(), parameter="k", values=[0.2, 0.4])
    assert out["status"] == "APPROVAL_REQUIRED"


def test_local_bifurcation_refuses_unknown_parameter():
    with pytest.raises(ValueError, match="unknown parameter"):
        diag.bifurcation_scan(
            _decay_model(), parameter="unsupported", values=[0.2, 0.4],
            approve_heavy=True,
        )


def test_real_stable_ode_scan_has_no_false_positive_bifurcation_claim():
    out = diag.bifurcation_scan(
        _decay_model(), parameter="k", values=[0.2, 0.4], approve_heavy=True,
    )
    assert out["status"] == "PASS"
    assert len(out["rows"]) == 2
    assert all(row["status"] == "PASS" for row in out["rows"])
    assert all(row["stability"]["max_real_part"] < 0 for row in out["rows"])
    assert out["transition_candidates"] == []


def test_failed_equilibrium_calculation_is_explicitly_recorded(monkeypatch):
    def fail(*args, **kwargs):
        raise ArithmeticError("no justified equilibrium")
    monkeypatch.setattr(diag, "_equilibrium_for_ode", fail)
    out = diag.bifurcation_scan(
        _decay_model(), parameter="k", values=[0.2, 0.4], approve_heavy=True,
    )
    assert out["status"] == "FAIL"
    assert len(out["rows"]) == 2
    assert all(row["status"] == "FAIL" for row in out["rows"])
    assert out["transition_candidates"] == []
