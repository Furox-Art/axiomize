"""Direct probabilistic benchmark uses only wheel-shipped SIR implementation."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.benchmark_suite import _case_08, run_suite
from axiomize.tools.numerical.gillespie import gillespie_sir_once


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ((float("nan"), 0.1, 1, 5000), "finite"),
        ((0.3, float("inf"), 1, 5000), "finite"),
        ((0.3, 0.0, 1, 5000), "positive"),
        ((-0.3, 0.1, 1, 5000), "non-negative"),
        ((0.3, 0.1, True, 5000), "integer"),
        ((0.3, 0.1, 1.5, 5000), "integer"),
        ((0.3, 0.1, 1, -5), "in"),
        ((0.3, 0.1, 6, 5), "I0"),
        ((0.3, 0.1, 1, 1_000_001), "in"),
    ],
)
def test_stochastic_sir_rejects_invalid_parameter_domains(args: tuple, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        gillespie_sir_once(*args)


def test_stochastic_sir_population_is_conserved_and_reproducible() -> None:
    one = gillespie_sir_once(0.3, 0.1, 1, 100, rng=np.random.default_rng(17))
    two = gillespie_sir_once(0.3, 0.1, 1, 100, rng=np.random.default_rng(17))
    assert one == two
    assert one["events"] <= 200
    assert 0 <= one["final_R"] <= one["total_infected"] <= 100
    assert one["total_infected"] >= 1  # includes the initial infection
    assert 1 <= one["peak_I"] <= 100
    assert math.isfinite(one["t_end"])


def test_stochastic_sir_extinction_semantics_and_zero_initial_cases() -> None:
    result = gillespie_sir_once(0.3, 0.1, 0, 100, rng=np.random.default_rng(0))
    assert result["events"] == 0
    assert result["extinct_early"] is True
    assert result["final_R"] == 0
    assert result["total_infected"] == 0
    assert result["peak_I"] == 0
    assert result["t_end"] == 0.0


def test_actual_stochastic_scientific_benchmark_passes() -> None:
    # This ran 11/12 in the previous released code because the package
    # attempted to import a checkout-only axiomize.tools.validate module.
    _case_08()


def test_all_twelve_package_native_benchmarks_pass_without_mocking() -> None:
    actual = run_suite()
    assert actual["status"] == "PASS", actual["results"]
    assert actual["passed"] == 12
    assert actual["total"] == 12
    assert {row["name"] for row in actual["results"]} == {
        "deterministic_model",
        "nonlinear_ode_outbreak",
        "optimization",
        "regression",
        "bayesian_fitting",
        "network_model",
        "control_problem",
        "stochastic_model",
        "pde_convergence",
        "wrong_model_rejected",
        "missing_information_explicit",
        "multiple_models_compared",
    }
