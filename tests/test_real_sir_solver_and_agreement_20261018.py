"""Physical SIR-domain and independent numerical-solver agreement contracts."""
from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.tools.numerical import scipy_tool as S


def valid_sir():
    return dict(beta=0.3, gamma=0.1, I0=10, N=1000,
                days=15, rtol=1e-8, atol=1e-10)


@pytest.mark.parametrize("field, value, fragment", [
    ("beta", -0.1, "beta must be"),
    ("gamma", -0.1, "gamma must be"),
    ("beta", 1e9, "beta must be"),
    ("gamma", 1e9, "gamma must be"),
    ("N", 0, "population"),
    ("N", -1, "population"),
    ("I0", -1, "I0 must"),
    ("I0", 1001, "I0 must"),
    ("days", 0, "days must"),
    ("days", -2, "days must"),
    ("rtol", 1e-16, "rtol must"),
    ("atol", 1e-18, "atol must"),
    ("rtol", 2, "rtol must"),
    ("atol", 2, "atol must"),
    ("beta", float("nan"), "finite"),
    ("gamma", float("inf"), "finite"),
    ("I0", "invalid", "numeric"),
])
def test_real_sir_parameter_contract_rejects_unphysical_inputs(field,value,fragment):
    values=valid_sir()
    values[field]=value
    with pytest.raises(ValueError,match=fragment):
        S._validate_sir_parameters(**values)


def test_sir_vector_field_conserves_population_analytically():
    derivatives=S._sir_rhs(0,[800,200,0],0.3,0.1,1000)
    assert len(derivatives)==3
    assert sum(derivatives)==pytest.approx(0.0)
    assert derivatives[2]==pytest.approx(20.0)


def test_real_sir_integrator_is_conservative_and_bounded():
    out=S.solve_sir(0.3,0.1,10,1000,days=5.0)
    assert out.success is True
    assert out.method=="RK45"
    assert out.y.shape==(3,2000)
    assert out.max_conservation_error < 1e-5
    assert out.max_residual < 1e-3
    assert 0.0 <= out.final_size <= 1.0


def test_explicit_sir_method_rejects_unknown_algorithm():
    with pytest.raises(ValueError,match="method must be"):
        S.solve_sir(0.3,0.1,10,1000,days=2,method="unreviewed")


@pytest.mark.parametrize("reproduction, expected", [
    (0.0,0.0),
    (0.5,0.0),
    (1.0,0.0),
])
def test_non_supercritical_final_size_is_exact_zero(reproduction,expected):
    assert S.final_size_numeric(reproduction,1.0)==expected


def test_final_size_rejects_nonpositive_recovery_rate():
    with pytest.raises(ValueError,match="gamma must be positive"):
        S.final_size_numeric(0.3,0.0)


def test_adapter_enforces_required_domain_fields():
    tool=S.SciPyTool()
    with pytest.raises(ValueError,match="payload must be an object"):
        tool.validate_input(None)
    for payload in ({}, {"beta":0.3}, {"beta":0.3,"gamma":0.1}):
        with pytest.raises(ValueError,match="needs"):
            tool.validate_input(payload)


def test_adapter_rejects_unsupported_solver_method_and_action():
    tool=S.SciPyTool()
    payload={"beta":0.3,"gamma":0.1,"N":1000,"method":"not-a-solver"}
    with pytest.raises(ValueError,match="method must be"):
        tool.validate_input(payload)
    with pytest.raises(ValueError,match="unknown action"):
        tool.execute({"action":"arbitrary"})


def test_adapter_returns_real_physical_diagnostics():
    result=S.SciPyTool().execute({"beta":0.3,"gamma":0.1,"I0":10,
                                  "N":1000,"days":5})
    assert result["success"] is True
    assert 0 <= result["final_size"] <= 1
    assert result["max_conservation_error"] < 1e-5


def ode_result(final_size):
    return S.OdeResult(True,"RK45",np.array([0,1]),np.zeros((3,2)),
                       final_size,0.0,0.0)


def test_independent_solvers_agree_within_declared_tolerance():
    agreed,difference=S.check_solver_agreement(ode_result(0.2),
                                                 ode_result(0.2002),
                                                 tolerance=1e-3)
    assert agreed is True
    assert difference==pytest.approx(0.0002)


def test_solver_agreement_refuses_large_discrepancy():
    agreed,difference=S.check_solver_agreement(ode_result(0.2),
                                                 ode_result(0.4),
                                                 tolerance=1e-3)
    assert agreed is False
    assert difference==pytest.approx(0.2)


def test_solver_agreement_refuses_nonfinite_solver_claim():
    for bad in (float("nan"),float("inf")):
        agreed,difference=S.check_solver_agreement(ode_result(bad),
                                                     ode_result(0.2))
        assert agreed is False
        assert math.isinf(difference)


@pytest.mark.parametrize("value, fragment", [
    (None, "numeric"),
    ("bad", "numeric"),
    (float("nan"), "finite and positive"),
    (0.0, "finite and positive"),
    (-0.1, "finite and positive"),
])
def test_agreement_threshold_must_be_finite_and_positive(value,fragment):
    with pytest.raises(ValueError,match=fragment):
        S.check_solver_agreement(ode_result(0.2),ode_result(0.2),tolerance=value)


def test_real_scipy_availability_version_is_not_guessed():
    tool=S.SciPyTool()
    assert isinstance(tool._probe_version(),str)
    assert tool._probe_version()
