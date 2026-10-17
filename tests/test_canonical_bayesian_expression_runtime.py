"""No hidden legacy Bayesian or unbounded SymPy code path remains."""

from __future__ import annotations

import math

import pytest

from axiomize import advanced_family_engine as advanced
from axiomize.bayesian.engine_v2 import _log_prior as canonical_log_prior
from axiomize.general_engine import _compile_expression_hardened
from axiomize.model_ir import ModelFamily, ModelIR, ParameterSpec, VariableSpec


def test_runtime_bayesian_prior_density_is_the_single_canonical_implementation():
    assert advanced._log_prior is canonical_log_prior


def test_runtime_expression_compiler_is_canonical_and_bounded():
    for expression in ("x+2", "sin(x)", "x**2"):
        compiled = advanced._compile_expression(expression, ["x"])
        hardened = _compile_expression_hardened(expression, ["x"])
        assert float(compiled(0.25)) == pytest.approx(float(hardened(0.25)), abs=1e-15)
    with pytest.raises(ValueError):
        advanced._compile_expression("9**(10**9)", ["x"])
    with pytest.raises(ValueError):
        advanced._compile_expression("__import__('os')", ["x"])


def test_runtime_bayesian_inference_uses_real_multichain_sampler():
    model = ModelIR(
        name="posterior",
        domain="statistics",
        family=ModelFamily.BAYESIAN,
        variables=[VariableSpec("y", role="output", initial=0.0)],
        parameters=[
            ParameterSpec("mu", 1.0, fit=True, prior={"dist": "normal", "mu": 0.0, "sigma": 3.0}),
        ],
        equations=[],
        metadata={
            "bayesian": {
                "observations": [1.0, 2.0, 1.5, 2.0],
                "mean_expression": "mu",
                "sigma": 0.5,
                "draws": 60,
                "burn": 20,
                "chains": 2,
            }
        },
    )
    result = advanced._infer_bayesian(model, t_span=(0.0, 1.0), points=5, parameter_overrides=None, seed=11)
    assert result["status"] == "PASS", result
    assert result["solver"]["method"] == "multi_chain_random_walk_metropolis"
    assert result["diagnostics"]["chains"] == 2
    assert result["diagnostics"]["finite"] is True
    assert result["posterior_predictive"]
    assert math.isfinite(result["posterior"]["mu"]["mean"])
