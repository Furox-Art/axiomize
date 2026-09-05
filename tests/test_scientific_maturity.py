from __future__ import annotations

import numpy as np
import pytest

from axiomize.bayesian.diagnostics import parameter_diagnostics, posterior_predictive_normal
from axiomize.general_engine import export_model, numerical_refinement, simulate_model
from axiomize.model_ir import ModelIR
from axiomize.tools.pde.fenics_tool import FEniCSAdapter


def _model(payload: dict) -> ModelIR:
    return ModelIR.from_dict({"schema_version": "1.0", "domain": "general", **payload})


def test_causal_engine_2_auto_backdoor_adjustment_and_effect() -> None:
    z = [0.,0.,0.,1.,1.,1.,0.,1.,0.,1.]
    t = [0.,0.,1.,0.,1.,1.,0.,1.,1.,1.]
    y = [1 + 3*zv + 2*tv for zv, tv in zip(z, t)]
    model = _model({
        "name":"causal-2", "family":"causal",
        "variables":[{"name":"y","role":"output","initial":0.0}], "parameters":[],
        "equations":[{"target":"y","kind":"causal","expression":"0"}],
        "metadata":{"causal":{"treatment":"t","outcome":"y","data":{"z":z,"t":t,"y":y},
                    "estimator":"robust_ols","identification":{"dag":[["z","t"],["z","y"],["t","y"]],"auto_adjustment":True}},
                    "numerical_verification":{"enabled":False}},
    })
    out = simulate_model(model)
    assert out["status"] == "PASS"
    assert out["identification"]["verified"] is True
    assert out["identification"]["adjustment_set"] == ["z"]
    assert out["causal_effect"]["estimate"] == pytest.approx(2.0, abs=1e-10)


def test_causal_engine_2_rejects_cyclic_dag() -> None:
    model = _model({
        "name":"cycle", "family":"causal", "variables":[{"name":"y","role":"output","initial":0}], "parameters":[],
        "equations":[{"target":"y","kind":"causal","expression":"0"}],
        "metadata":{"causal":{"treatment":"t","outcome":"y","data":{"t":[0,1,0,1],"y":[0,1,0,1]},
                    "identification":{"dag":[["t","y"],["y","t"]]}}},
    })
    with pytest.raises(ValueError, match="cycle"):
        simulate_model(model)


def test_bayesian_diagnostics_and_ppc_are_finite() -> None:
    rng = np.random.default_rng(123)
    chains = rng.normal(2.0, 0.2, size=(4, 1000))
    diag = parameter_diagnostics(chains)
    assert diag["r_hat"] < 1.05
    assert diag["ess_bulk"] > 100
    assert diag["mcse_mean"] > 0
    means = rng.normal(2.0, 0.05, size=(500, 5))
    ppc = posterior_predictive_normal(means, sigma_draws=np.full(500, 0.2), observed=np.full(5, 2.0), seed=7)
    assert ppc["status"] == "PASS"
    assert len(ppc["predictive_mean"]) == 5
    assert 0 <= ppc["interval_coverage"] <= 1


def test_native_bayesian_engine_returns_rhat_ess_mcse_and_ppc() -> None:
    model = _model({
        "name":"bayes-line", "family":"bayesian",
        "variables":[{"name":"y","role":"output","initial":0.0}],
        "parameters":[{"name":"a","value":1.5,"fit":True,"prior":{"dist":"normal","mu":0,"sigma":3}}],
        "equations":[{"target":"y","kind":"observation","expression":"a*x"}],
        "metadata":{"bayesian":{"data":{"x":[0.,1.,2.,3.,4.]},"observations":[0.,2.,4.,6.,8.],
                    "mean_expression":"a*x","sigma":0.2,"draws":250,"burn":80,"chains":2,"proposal_scale":{"a":0.08}},
                    "numerical_verification":{"enabled":False}},
    })
    out = simulate_model(model, seed=5, approve_heavy=True)
    assert out["status"] in {"PASS", "WARNING"}
    for key in ("r_hat", "ess_bulk", "mcse_mean"):
        assert key in out["posterior"]["a"]
    assert "posterior_predictive" in out
    assert out["posterior"]["a"]["mean"] == pytest.approx(2.0, abs=0.25)


def test_expanded_exports_are_nonempty_and_julia_is_family_scoped() -> None:
    model = _model({"name":"decay","family":"ode","variables":[{"name":"x","initial":1}],
                    "parameters":[{"name":"k","value":.2}],"equations":[{"target":"x","kind":"derivative","expression":"-k*x"}]})
    for fmt in ("latex", "mathml", "dot", "markdown", "julia"):
        out = export_model(model, format=fmt)
        assert out["status"] == "PASS"
        assert out["content"]
    algebraic = _model({"name":"root","family":"algebraic","variables":[{"name":"x","initial":1}],"parameters":[],
                        "equations":[{"target":"","kind":"residual","expression":"x-2"}]})
    assert export_model(algebraic, format="julia")["status"] == "ADAPTER_REQUIRED"


def test_all_family_numerical_verification_contract_is_explicit() -> None:
    model = _model({"name":"root","family":"algebraic","variables":[{"name":"x","initial":1}],"parameters":[],
                    "equations":[{"target":"","kind":"residual","expression":"x-2"}]})
    blocked = numerical_refinement(model, approve_heavy=False)
    assert blocked["status"] == "APPROVAL_REQUIRED"
    checked = numerical_refinement(model, approve_heavy=True)
    assert checked["status"] == "PASS"
    assert checked["study"] == "deterministic_repeatability"


def test_fenics_executor_has_real_declarative_contract() -> None:
    tool = FEniCSAdapter()
    tool.validate_input({"problem":"poisson_1d","domain":[0,1],"cells":8,"degree":1,"source":2,"dirichlet":{"left":0,"right":0}})
    with pytest.raises(ValueError):
        tool.validate_input({"problem":"arbitrary_weak_form","weak_form":"exec(...)"})
    meta = tool.availability()
    if meta.available:
        out = tool.execute({"problem":"poisson_1d","cells":8,"source":2.0})
        assert out["status"] == "PASS"
        assert out["diagnostics"]["dofs"] >= 9
        assert np.isfinite(out["diagnostics"]["l2_error"])
