from __future__ import annotations

import numpy as np
import pytest

from axiomize.general_engine import export_model, numerical_refinement, simulate_model
from axiomize.model_ir import ModelFamily, ModelIR
from axiomize.scientific_stress import _models
from axiomize.tools.pde.fenics_tool import FEniCSAdapter


def _model(payload:dict)->ModelIR:
    return ModelIR.from_dict({"schema_version":"1.0","domain":"general",**payload})


def test_numerical_verification_contract_covers_every_family_and_is_approval_gated() -> None:
    models=_models()
    assert set(models)==set(ModelFamily)
    for family,model in models.items():
        result=numerical_refinement(model,t_span=(0,1),points=10,seed=4,approve_heavy=False)
        assert result["status"]=="APPROVAL_REQUIRED", family.value
        assert result["uncertainty_separation"]["numerical"]


def test_causal_engine_2_randomized_aipw_and_dag_cycle_guard() -> None:
    model=_model({
        "name":"causal2","family":"causal",
        "variables":[{"name":"y","role":"output","initial":0.0}],"parameters":[],
        "equations":[{"target":"y","expression":"0","kind":"causal"}],
        "metadata":{"causal":{"treatment":"t","outcome":"yobs","data":{"t":[0,1,0,1,0,1,0,1],"yobs":[1,3,1,3,1,3,1,3]},
                              "identification":{"randomized":True},"intervention_values":[0,1]}}
    })
    result=simulate_model(model)
    assert result["status"]=="PASS"
    assert result["causal_effect"]["method"].startswith("aipw")
    assert result["causal_effect"]["estimate"]==pytest.approx(2.0,abs=1e-10)
    assert len(result["counterfactuals"])==2

    cyclic=model.to_dict(); cyclic["metadata"]["causal"]["identification"]={"identified_dag":True,"dag_edges":[["t","z"],["z","t"]]}
    with pytest.raises(ValueError,match="cycle"):
        simulate_model(ModelIR.from_dict(cyclic))


def test_bayesian_engine_2_surfaces_multichain_diagnostics_and_ppc() -> None:
    model=_model({
        "name":"bayes2","family":"bayesian","variables":[{"name":"y","role":"output","initial":0.0}],
        "parameters":[{"name":"a","value":1.8,"fit":True,"prior":{"dist":"normal","mu":0,"sigma":3}}],
        "equations":[{"target":"y","expression":"a*x","kind":"observation"}],
        "metadata":{"bayesian":{"data":{"x":[0,1,2,3,4]},"observations":[0,2,4,6,8],"mean_expression":"a*x","sigma":.2,
                                "draws":160,"burn":60,"chains":2,"proposal_scale":{"a":.08}},"numerical_verification":{"enabled":False}}
    })
    blocked=simulate_model(model,seed=7)
    assert blocked["status"]=="APPROVAL_REQUIRED"
    result=simulate_model(model,seed=7,approve_heavy=True)
    assert result["status"]=="PASS"
    assert result["posterior"]["a"]["mean"]==pytest.approx(2.0,abs=.2)
    diag=result["diagnostics"]
    assert diag["chains"]==2 and "acceptance_rate" in diag
    assert "r_hat" in diag["posterior"]["parameters"]["a"]
    ppc=result["posterior_predictive"]
    assert 0<=ppc["coverage95"]<=1 and ppc["replications"]>=10


def test_extended_exports_are_real_and_family_scoped() -> None:
    models=_models()
    mo=export_model(models[ModelFamily.ODE],format="modelica-3.6")
    assert mo["status"]=="PASS" and "der(x)" in mo["content"]
    graph=export_model(models[ModelFamily.NETWORK],format="graphml")
    assert graph["status"]=="PASS" and "graphml" in graph["content"]
    dot=export_model(models[ModelFamily.CAUSAL],format="causal-dot")
    assert dot["status"]=="PASS" and dot["content"].startswith("digraph")
    bundle=export_model(models[ModelFamily.ODE],format="portable-bundle-v1")
    assert bundle["status"]=="PASS" and len(bundle["bundle"]["sha256"])==64
    unsupported=export_model(models[ModelFamily.BAYESIAN],format="modelica-3.6")
    assert unsupported["status"]=="ADAPTER_REQUIRED"


def test_fenics_structured_executor_never_accepts_arbitrary_weak_form_text() -> None:
    tool=FEniCSAdapter()
    tool.validate_input({"problem":"poisson","dimension":1,"cells":8,"source":1.0,"dirichlet":0.0,"degree":1})
    with pytest.raises(ValueError):tool.validate_input({"problem":"poisson","dimension":1,"cells":1})
    with pytest.raises(ValueError):tool.validate_input({"problem":"custom","weak_form":"__import__('os')"})
    meta=tool.availability()
    if meta.available:
        result=tool.execute({"problem":"poisson","dimension":1,"cells":8,"source":1.0,"dirichlet":0.0,"degree":1})
        assert result["status"]=="PASS" and result["solution"]["finite"] is True
