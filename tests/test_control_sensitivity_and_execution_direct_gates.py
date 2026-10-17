"""Direct scientific PID, Monte Carlo, and trusted subprocess safety contracts."""

from __future__ import annotations

import json
import math

import pytest

from axiomize.control.pid import _finite as control_finite
from axiomize.control.pid import _poly, closed_loop_step
from axiomize.execution.sandbox import (
    UnsafeExecutionDenied,
    _child_environment,
    run_python,
)
from axiomize.sensitivity.analysis import (
    _validated_params,
    local_sensitivity,
    mc_sensitivity,
)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("not-real", "numeric"),
        (None, "numeric"),
        (float("nan"), "finite"),
        (float("inf"), "finite"),
    ],
)
def test_control_scalar_parameters_are_finite_observed_numbers(value, message):
    with pytest.raises(ValueError, match=message):
        control_finite(value, name="kp")


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ([], "coefficients"),
        ([[1.0, 2.0]], "coefficients"),
        (["not-real"], "numeric 1D"),
        ([float("nan")], "finite"),
        ([float("inf")], "finite"),
    ],
)
def test_control_plant_polynomial_never_silently_coerces_bad_coefficients(values, message):
    with pytest.raises(ValueError, match=message):
        _poly(values, name="plant", allow_all_zero=True)


def test_control_plant_denominator_is_not_the_zero_polynomial():
    with pytest.raises(ValueError, match="zero polynomial"):
        _poly([0.0, 0.0], name="plant_den", allow_all_zero=False)


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({}, "1.."),
        ({"a": "n/a"}, "numeric"),
        ({"a": float("inf")}, "finite"),
    ],
)
def test_local_sensitivity_requires_explicit_finite_parameters(params, message):
    with pytest.raises(ValueError, match=message):
        _validated_params(params)


def test_local_derivatives_match_analytic_multiplicative_model():
    def model(p):
        return 2 * p["a"] * p["b"] ** 2

    result = local_sensitivity(model, {"a": 3.0, "b": 4.0}, rel_step=1e-6)
    assert result["a"] == pytest.approx(1.0, abs=1e-5)
    assert result["b"] == pytest.approx(2.0, abs=1e-4)


@pytest.mark.parametrize("step", [-0.01, 0.0, 1.1, float("nan")])
def test_finite_difference_step_must_be_positive_bounded_and_finite(step):
    with pytest.raises(ValueError, match="rel_step"):
        local_sensitivity(lambda values: values["a"], {"a": 1.0}, rel_step=step)


def test_local_sensitivity_zero_baseline_is_explicitly_handled():
    assert local_sensitivity(lambda p: p["a"] - 1.0, {"a": 1.0})["a"] == pytest.approx(1.0)


def test_local_sensitivity_nonfinite_model_output_fails_before_reporting():
    with pytest.raises(ValueError, match="base model output must be finite"):
        local_sensitivity(lambda p: float("nan"), {"a": 1.0})


@pytest.mark.parametrize(
    ("bounds", "message"),
    [
        ({}, "1.."),
        ({"a": [0]}, "low, high"),
        ({"a": [1, 0]}, "high must exceed"),
        ({"a": [0, float("nan")]}, "finite"),
        ({"a": ["not-numeric", 1]}, "numeric"),
    ],
)
def test_monte_carlo_parameter_ranges_refuse_invalid_or_unbounded_models(bounds, message):
    with pytest.raises(ValueError, match=message):
        mc_sensitivity(lambda p: p.get("a", 1.0), bounds, n=10, seed=2)


def test_monte_carlo_correlations_are_seed_reproducible_and_normalized():
    def model(p):
        return 4 * p["a"] + p["b"]

    bounds = {"a": (0.0, 1.0), "b": (0.0, 1.0)}
    left = mc_sensitivity(model, bounds, n=250, seed=4)
    right = mc_sensitivity(model, bounds, n=250, seed=4)
    assert left == right
    assert left["a"] > left["b"]
    assert sum(left.values()) == pytest.approx(1.0)


def test_constant_response_does_not_fabricate_nonzero_parameter_importance():
    indices = mc_sensitivity(lambda p: 2.0, {"a": (0.0, 1.0)}, n=20, seed=1)
    assert indices == {"a": 0.0}


def test_trusted_execution_is_denied_by_default_even_for_trivial_code():
    with pytest.raises(UnsafeExecutionDenied, match="disabled by default"):
        run_python("print(2+2)")


@pytest.mark.parametrize(
    ("code", "timeout", "message"),
    [
        (None, 10.0, "code must be a string"),
        ("print(1)", 0.0, "timeout_s"),
        ("print(1)", float("nan"), "timeout_s"),
        ("print(1)", 3601.0, "timeout_s"),
    ],
)
def test_trusted_execution_inputs_require_explicit_bounded_resources(code, timeout, message):
    with pytest.raises(ValueError, match=message):
        run_python(code, timeout_s=timeout, allow_unsafe_code=True)


def test_isolated_execution_does_not_inherit_ambient_secret_even_after_opt_in(monkeypatch):
    monkeypatch.setenv("AXIOMIZE_TEST_PRIVATE_TOKEN", "not-for-subprocess")
    env = _child_environment("/sandbox", seed=3, inherit=False)
    assert "AXIOMIZE_TEST_PRIVATE_TOKEN" not in env
    assert env["HOME"] == "/sandbox"
    assert env["AXIOMIZE_SEED"] == "3"
    assert env["PYTHONHASHSEED"] == "3"


def test_inherited_environment_requires_explicit_second_permission_and_strips_python_controls(monkeypatch):
    monkeypatch.setenv("AXIOMIZE_TEST_PRIVATE_TOKEN", "permitted-by-opt-in")
    monkeypatch.setenv("PYTHONPATH", "/untrusted")
    env = _child_environment("/sandbox", seed=None, inherit=True)
    assert env["AXIOMIZE_TEST_PRIVATE_TOKEN"] == "permitted-by-opt-in"
    assert "PYTHONPATH" not in env
    assert "PYTHONHASHSEED" not in env


def test_approved_python_executes_real_isolated_child_and_records_provenance(monkeypatch):
    monkeypatch.setenv("AXIOMIZE_TEST_PRIVATE_TOKEN", "should-not-leak")
    result = run_python(
        "import os, json; print(json.dumps({'secret':os.getenv('AXIOMIZE_TEST_PRIVATE_TOKEN'),"
        "'seed':os.getenv('AXIOMIZE_SEED'), 'cwd':os.path.basename(os.getcwd())}))",
        timeout_s=10,
        seed=7,
        allow_unsafe_code=True,
    )
    assert result.exit_code == 0
    assert result.timed_out is False
    data = json.loads(result.stdout)
    assert data["secret"] is None
    assert data["seed"] == "7"
    assert data["cwd"].startswith("axiomize_exec_")
    assert result.environment_inherited is False
    assert result.tool_versions["python"]
    assert result.artifacts == []


def test_real_control_step_uses_scientific_backend_and_keeps_bounded_final():
    out = closed_loop_step(
        1.0,
        0.1,
        0.0,
        plant_num=[1.0],
        plant_den=[1.0, 1.0],
        t_end=30.0,
        n=100,
    )
    assert out["points"] == 100
    assert math.isfinite(out["final"])
    assert math.isfinite(out["overshoot"])
    assert out["overshoot"] >= 0.0
    assert isinstance(out["settled"], bool)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"plant_den": [0.0]}, "zero polynomial"),
        ({"t_end": 0.0}, "t_end"),
        ({"t_end": float("inf")}, "finite"),
        ({"n": 1}, "control output points"),
        ({"kp": float("nan")}, "kp"),
    ],
)
def test_control_solver_rejects_invalid_model_and_horizon_before_execution(change, message):
    data = dict(kp=1.0, ki=0.1, kd=0.0, plant_num=[1.0], plant_den=[1.0, 1.0], t_end=10.0, n=30)
    data.update(change)
    with pytest.raises(ValueError, match=message):
        closed_loop_step(**data)
