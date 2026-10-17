"""Direct partitioned cosimulation tests with explicit coupling provenance."""

from __future__ import annotations

import copy
import math

import pytest

from axiomize.advanced_family_engine import _simulate_multiphysics
from axiomize.general_engine import simulate_model
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, VariableSpec


@pytest.fixture
def component_models():
    source = ModelIR(
        name="source",
        domain="physics",
        family=ModelFamily.ODE,
        variables=[VariableSpec("x", initial=2.0)],
        parameters=[],
        equations=[EquationSpec("x", "0")],
    )
    target = ModelIR.from_dict(
        {
            "schema_version": "1.0",
            "name": "target",
            "domain": "physics",
            "family": "ode",
            "variables": [{"name": "y", "initial": 1.0}],
            "parameters": [{"name": "k", "value": 1.0}],
            "equations": [{"target": "y", "kind": "derivative", "expression": "-k*y"}],
        }
    )
    return source.to_dict(), target.to_dict()


@pytest.fixture
def coupling():
    return {
        "from_component": "source",
        "from_state": "x",
        "to_component": "target",
        "to_parameter": "k",
        "reduction": "final",
        "scale": 0.5,
    }


def _model(source, target, *, cfg=None):
    data = {"components": {"source": source, "target": target}, "couplings": []}
    if cfg:
        data.update(cfg)
    return ModelIR(
        name="composed",
        domain="physics",
        family=ModelFamily.MULTIPHYSICS,
        variables=[VariableSpec("q", initial=0.0)],
        parameters=[],
        equations=[EquationSpec("q", "0", kind="coupling")],
        metadata={"multiphysics": data},
    )


def _run(model, executor=simulate_model):
    return _simulate_multiphysics(
        model, t_span=(0.0, 0.5), points=6, parameter_overrides=None, seed=11, simulate_fn=executor
    )


def test_uncoupled_components_preserve_separate_exact_solutions(component_models):
    source, target = component_models
    out = _run(_model(source, target))
    assert out["status"] == "PASS", out
    assert out["diagnostics"]["converged"] is True
    assert out["states"]["q"] == 0.0
    assert out["components"]["source"]["states"]["x"][-1] == pytest.approx(2.0)
    assert out["components"]["target"]["states"]["y"][-1] == pytest.approx(math.exp(-0.5), rel=1e-5)


def test_bound_coupling_uses_explicit_final_state_and_fixed_point_convergence(component_models, coupling):
    source, target = component_models
    out = _run(_model(source, target, cfg={"couplings": [coupling], "max_iterations": 4, "tolerance": 1e-8}))
    assert out["status"] == "PASS", out
    assert out["diagnostics"]["converged"] is True
    assert out["coupling_overrides"]["target"]["k"] == pytest.approx(1.0)
    assert len(out["convergence"]) == 2
    assert out["components"]["target"]["states"]["y"][-1] == pytest.approx(math.exp(-0.5), rel=1e-5)


@pytest.mark.parametrize(
    ("cfg", "message"),
    [
        ({"components": {}}, "at least two"),
        ({"components": 42}, "must be an object or array"),
        ({"components": [{"name": "source"}]}, "at least two"),
        ({"components": [{"name": "source", "model_ir": {}}, {}]}, "need name"),
        ({"components": {"source": "invalid", "target": {}}}, "must contain Model IR"),
        ({"couplings": "bad"}, "couplings must be an array"),
        ({"max_iterations": 0}, "must be between"),
        ({"max_iterations": 101}, "must be between"),
        ({"couplings": [None]}, "must be an object"),
    ],
)
def test_malformed_multiphysics_contracts_cannot_silently_succeed(component_models, cfg, message):
    source, target = component_models
    m = _model(source, target, cfg=cfg)
    with pytest.raises(ValueError, match=message):
        _run(m)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"from_component": "missing"}, "unknown component"),
        ({"to_component": "missing"}, "unknown component"),
        ({"from_state": "missing"}, "source state"),
        ({"to_parameter": "missing"}, "target parameter"),
    ],
)
def test_coupling_rejects_unobserved_sources_and_unknown_targets(component_models, coupling, change, message):
    source, target = component_models
    binding = {**coupling, **change}
    m = _model(source, target, cfg={"couplings": [binding]})
    with pytest.raises(ValueError, match=message):
        _run(m)


def test_component_failure_is_reported_not_hidden_by_other_components(component_models):
    source, target = component_models
    m = _model(source, target)

    def failure(_component, **_kwargs):
        return {"status": "FAIL", "stage": "solver"}

    out = _run(m, executor=failure)
    assert out["status"] == "FAIL"
    assert out["stage"] == "component_execution"
    assert out["component"] == "source"
    assert out["component_result"]["stage"] == "solver"


def test_fixed_point_iteration_limit_returns_explicit_nonconvergence(component_models, coupling):
    source, target = component_models
    m = _model(source, target, cfg={"couplings": [coupling], "max_iterations": 1})
    out = _run(m)
    assert out["status"] == "FAIL"
    assert out["stage"] == "coupling_convergence"
    assert len(out["convergence"]) == 1


def test_nested_multiphysics_is_rejected(component_models):
    source, target = component_models
    inner = copy.deepcopy(source)
    inner["family"] = "multiphysics"
    m = _model(inner, target)
    with pytest.raises(ValueError, match="nested multiphysics"):
        _run(m)
