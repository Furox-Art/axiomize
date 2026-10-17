"""Native ODE solver checks: physical units, parameter bounds and authentic fallbacks."""

from __future__ import annotations

import math

import pytest

from axiomize.general_engine_core import (
    _parameter_values,
    _simulate_ode,
    infer_domain,
    recommend_model_families,
    select_solver,
    simulate_model,
)
from axiomize.model_ir import (
    EquationSpec,
    ModelFamily,
    ModelIR,
    ParameterSpec,
    SolverSpec,
    VariableSpec,
)


def valid_decay(*, initial=1.0, parameter=1.0, solver=None):
    return ModelIR(
        name="measured decay",
        domain="physics",
        family=ModelFamily.ODE,
        variables=[VariableSpec("x", initial=initial)],
        parameters=[ParameterSpec("k", value=parameter, bounds=(0.0, 2.0))],
        equations=[EquationSpec("x", "-k*x", kind="derivative")],
        independent_unit="dimensionless",
        solver=solver or SolverSpec(),
    )


@pytest.mark.parametrize(
    ("kw", "pattern"),
    [
        ({"parameter": None}, "has no value"),
    ],
)
def test_unknown_model_parameter_cannot_be_replaced_with_a_guess(kw, pattern):
    m = valid_decay(**kw)
    with pytest.raises(ValueError, match=pattern):
        _parameter_values(m)


@pytest.mark.parametrize(
    ("overrides", "pattern"),
    [
        ({"k": -0.1}, "below lower bound"),
        ({"k": 2.1}, "above upper bound"),
        ({"invented": 2.0}, "unknown parameter overrides"),
    ],
)
def test_parameter_override_refuses_unknown_or_out_of_domain_values(overrides, pattern):
    m = valid_decay()
    with pytest.raises(ValueError, match=pattern):
        _parameter_values(m, overrides)


def test_parameter_override_is_accepted_only_within_declared_interval():
    m = valid_decay()
    assert _parameter_values(m, {"k": 1.8}) == {"k": 1.8}


@pytest.mark.parametrize(
    ("span", "pattern"),
    [
        ((2.0, 2.0), "finite and increasing"),
        ((2.0, 1.0), "finite and increasing"),
        ((0.0, float("nan")), "finite and increasing"),
    ],
)
def test_ode_time_interval_must_be_finite_and_increasing(span, pattern):
    with pytest.raises(ValueError, match=pattern):
        _simulate_ode(valid_decay(), t_span=span, points=20, parameter_overrides=None)


def test_missing_ode_initial_state_is_not_inferred():
    with pytest.raises(ValueError, match="needs an initial value"):
        _simulate_ode(valid_decay(initial=None), t_span=(0.0, 1.0), points=12, parameter_overrides=None)


def test_real_decay_solution_approximates_analytic_state():
    m = valid_decay(parameter=1.0)
    result = _simulate_ode(m, t_span=(0.0, 2.0), points=101, parameter_overrides=None)
    assert result["status"] == "PASS", result
    assert result["states"]["x"][-1] == pytest.approx(math.exp(-2), abs=3e-4)
    assert result["diagnostics"]["finite"] is True
    assert result["time"][0] == 0.0
    assert result["time"][-1] == 2.0


def test_native_solver_failure_is_explicit_and_records_every_attempt(monkeypatch):
    from scipy import integrate

    def fails(*a, **kw):
        raise RuntimeError("numerical integration unavailable")

    monkeypatch.setattr(integrate, "solve_ivp", fails)
    out = _simulate_ode(valid_decay(), t_span=(0.0, 1.0), points=10, parameter_overrides=None)
    assert out["status"] == "FAIL"
    assert out["stage"] == "solve"
    assert len(out["solver_attempts"]) >= 1
    assert all("integration unavailable" in i["message"] for i in out["solver_attempts"])


def test_solver_safely_switches_to_verified_fallback_after_observed_failure(monkeypatch):
    from scipy import integrate

    original = integrate.solve_ivp
    calls = []

    def intermittent(*args, **kwargs):
        calls.append(kwargs.get("method"))
        if len(calls) == 1:
            raise RuntimeError("first solver backend failed")
        return original(*args, **kwargs)

    monkeypatch.setattr(integrate, "solve_ivp", intermittent)
    out = _simulate_ode(valid_decay(), t_span=(0.0, 1.0), points=21, parameter_overrides=None)
    assert out["status"] == "PASS"
    assert out["solver"]["attempts"][0]["success"] is False
    assert out["solver"]["attempts"][1]["success"] is True
    assert len(calls) == 2


def test_unrecognized_solver_method_is_not_executed_as_arbitrary_command():
    m = valid_decay(solver=SolverSpec(backend="custom", method="malicious-exe", fallbacks=()))
    out = _simulate_ode(m, t_span=(0.0, 1.0), points=11, parameter_overrides=None)
    assert out["status"] == "PASS"
    assert out["solver"]["method"] == "DOP853"


@pytest.mark.parametrize(
    ("phrase", "expected_domain"),
    [
        ("A random unrelated thought", "general"),
        ("population cells and proteins", "biology"),
        ("Oscillation of quantum field energy", "physics"),
        ("portfolio volatility market returns", "finance"),
    ],
)
def test_domain_hints_are_explicit_token_matches_not_inferred_evidence(phrase, expected_domain):
    assert infer_domain(phrase)["domain"] == expected_domain


@pytest.mark.parametrize(
    ("idea", "family"),
    [
        ("Noisy stochastic fluctuations", "stochastic"),
        ("Contact network spread", "network"),
        ("Optimal portfolio allocation", "optimization"),
        ("Bayesian posterior inference", "bayesian"),
    ],
)
def test_signal_recommendation_only_proposes_family_not_made_up_equations(idea, family):
    out = recommend_model_families(idea=idea)
    assert any(item["family"] == family for item in out)
    assert all("equation" not in item for item in out)


def test_explicit_solver_method_is_preserved_without_silent_inference():
    m = valid_decay(solver=SolverSpec(backend="scipy", method="BDF", fallbacks=("RK45",)))
    picked = select_solver(m)
    assert picked["backend"] == "scipy"
    assert picked["method"] == "BDF"
    assert picked["fallbacks"] == ["RK45"]


def test_no_silent_family_fallback_to_a_different_simulator():
    m = valid_decay()
    m.family = ModelFamily.CONTROL
    with pytest.raises(ValueError, match="control state-space matrix missing: A"):
        simulate_model(m, t_span=(0.0, 1.0), points=9)
