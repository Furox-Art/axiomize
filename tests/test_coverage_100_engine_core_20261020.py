"""Coverage-completing tests for the generic engine core.

The public facade rebinds several core globals to hardened wrappers, so this
module loads the shipped ``general_engine_core.py`` source directly and tests
the originally defined functions, including their validation branches.
"""

from __future__ import annotations

import importlib.util
import math
import sys
import types

import numpy as np
import pytest
import scipy.integrate
import sympy as sp

import axiomize.general_engine_core as _shipped_core
from axiomize.model_ir import (
    ConstraintSpec,
    EquationSpec,
    ModelFamily,
    ModelIR,
    ParameterSpec,
    VariableSpec,
)


def _load_core():
    spec = importlib.util.spec_from_file_location(
        "axiomize_general_engine_core_native", _shipped_core.__file__
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = _load_core()


def _model(payload: dict) -> ModelIR:
    return ModelIR.from_dict({"schema_version": "1.0", "domain": "general", **payload})


def _ode_model(*, value=1.0, fit=False, initial=1.0, bounds=None, metadata=None) -> ModelIR:
    parameter = {"name": "k", "value": value, "fit": fit}
    if bounds is not None:
        parameter["bounds"] = bounds
    return _model({
        "name": "ode-coverage",
        "family": "ode",
        "variables": [{"name": "x", "initial": initial}],
        "parameters": [parameter],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
        "metadata": metadata or {},
    })


def test_token_matching_requires_word_boundary() -> None:
    tokens = frozenset({"ecosystem"})
    assert core.term_present("system", text="ecosystem", tokens=tokens) is False
    assert core.term_present("system", text="system", tokens=frozenset({"system"})) is True
    assert core.term_present("", text="anything", tokens=tokens) is False
    assert core._token_matches("x", "system") is False


def test_family_recommendations_for_each_signal_group() -> None:
    optimization = core.recommend_model_families(signals=["optimization"])
    assert optimization[0]["family"] == "optimization"

    structure = core.recommend_model_families(signals=["network", "causal"])
    families = {row["family"] for row in structure}
    assert {"network", "causal"} <= families

    inference = core.recommend_model_families(signals=["event", "bayesian", "equilibrium"])
    selected = {row["family"] for row in inference}
    assert {"discrete_event", "bayesian", "algebraic"} <= selected


def test_build_execution_plan_fit_stages() -> None:
    plan = core.build_execution_plan(_ode_model(), action="fit", points=10)
    assert "identifiability_check" in plan["stages"]
    assert plan["stages"][-1] == "model_selection_scores"


def test_hardened_expression_parser_validation() -> None:
    x = sp.Symbol("x", real=True)
    with pytest.raises(SyntaxError):
        core._sympy_expression("x +", {"x": x})
    with pytest.raises(ValueError, match="unsupported expression syntax"):
        core._sympy_expression("x if x else 1", {"x": x})
    with pytest.raises(ValueError, match="unknown symbol"):
        core._sympy_expression("foo + x", {"x": x})
    with pytest.raises(ValueError, match="approved mathematical functions"):
        core._sympy_expression("foo(x)", {"x": x})
    expression = core._sympy_expression("sin(x) + 1", {"x": x})
    assert sp.simplify(expression - (sp.sin(x) + 1)) == 0


def test_parameter_value_validation() -> None:
    missing = _model({
        "name": "param-missing",
        "family": "ode",
        "variables": [{"name": "x", "initial": 1.0}],
        "parameters": [{"name": "k"}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    })
    with pytest.raises(ValueError, match="has no value"):
        core._parameter_values(missing)
    below = ModelIR(
        name="param-below",
        domain="general",
        family=ModelFamily.ODE,
        variables=[VariableSpec(name="x", initial=1.0)],
        parameters=[ParameterSpec(name="k", value=1.0, bounds=(2.0, 5.0))],
        equations=[EquationSpec(target="x", expression="-k*x", kind="derivative")],
    )
    with pytest.raises(ValueError, match="below lower bound"):
        core._parameter_values(below)
    above = ModelIR(
        name="param-above",
        domain="general",
        family=ModelFamily.ODE,
        variables=[VariableSpec(name="x", initial=1.0)],
        parameters=[ParameterSpec(name="k", value=5.0, bounds=(0.0, 2.0))],
        equations=[EquationSpec(target="x", expression="-k*x", kind="derivative")],
    )
    with pytest.raises(ValueError, match="above upper bound"):
        core._parameter_values(above)
    with pytest.raises(ValueError, match="unknown parameter overrides"):
        core._parameter_values(_ode_model(), {"nope": 1.0})
    assert core._parameter_values(_ode_model(), {"k": 2.0}) == {"k": 2.0}


def test_simulate_reports_structure_failure() -> None:
    invalid = ModelIR(
        name="",
        domain="general",
        family=ModelFamily.ODE,
        variables=[],
        parameters=[],
        equations=[],
    )
    out = core.simulate_model(invalid)
    assert out["status"] == "FAIL"
    assert out["stage"] == "structure"


def test_simulate_requires_approval_for_high_cost_pde() -> None:
    model = _model({
        "name": "pde-expensive",
        "family": "pde",
        "variables": [{"name": "u", "initial": 1.0}],
        "equations": [{"target": "u", "expression": "0", "kind": "derivative"}],
    })
    out = core.simulate_model(model, points=100_000)
    assert out["status"] == "APPROVAL_REQUIRED"
    assert out["cost"]["level"] == "high"
    assert out["plan"]["approval_required"] is True


def test_simulate_routes_unsupported_family() -> None:
    model = _model({
        "name": "control-route",
        "family": "control",
        "variables": [{"name": "x", "initial": 1.0}],
        "equations": [{"target": "x", "expression": "0", "kind": "state_space"}],
    })
    out = core.simulate_model(model)
    assert out["status"] == "TOOL_ROUTE_REQUIRED"
    assert out["family"] == "control"
    assert out["solver"]["backend"] == "control"


def test_ode_executor_validation_and_solver_failure(monkeypatch) -> None:
    with pytest.raises(ValueError, match="needs an initial value"):
        core._simulate_ode(_ode_model(initial=None), t_span=(0.0, 1.0), points=5,
                           parameter_overrides=None)
    with pytest.raises(ValueError, match="t_span must be finite and increasing"):
        core._simulate_ode(_ode_model(), t_span=(1.0, 0.0), points=5,
                           parameter_overrides=None)

    def exploding_solve(*args, **kwargs):
        raise RuntimeError("forced solver exception")

    monkeypatch.setattr(scipy.integrate, "solve_ivp", exploding_solve)
    out = core._simulate_ode(_ode_model(), t_span=(0.0, 1.0), points=5,
                             parameter_overrides=None)
    assert out["status"] == "FAIL"
    assert out["stage"] == "solve"
    assert len(out["solver_attempts"]) >= 3
    assert all("forced solver exception" in item["message"] for item in out["solver_attempts"])


def _sde_model(initial=1.0, metadata=None) -> ModelIR:
    return _model({
        "name": "sde-coverage",
        "family": "stochastic",
        "variables": [{"name": "x", "initial": initial}],
        "parameters": [],
        "equations": [{"target": "x", "expression": "0", "kind": "derivative"}],
        "metadata": metadata or {},
    })


def test_sde_validation_branches() -> None:
    with pytest.raises(ValueError, match="finite initial values"):
        core._simulate_sde(_sde_model(initial=None), t_span=(0.0, 1.0), points=5,
                           parameter_overrides=None, seed=1)
    with pytest.raises(ValueError, match="t_span must be increasing"):
        core._simulate_sde(_sde_model(), t_span=(2.0, 1.0), points=5,
                           parameter_overrides=None, seed=1)
    with pytest.raises(ValueError, match="diffusion must be an object"):
        core._simulate_sde(_sde_model(metadata={"diffusion": []}), t_span=(0.0, 1.0),
                           points=5, parameter_overrides=None, seed=1)


def _constrained_relation(relation: str, upper=None) -> ModelIR:
    return ModelIR(
        name="constraint-coverage",
        domain="general",
        family=ModelFamily.ODE,
        variables=[VariableSpec(name="x", initial=1.0)],
        parameters=[],
        equations=[EquationSpec(target="x", expression="0", kind="derivative")],
        constraints=[ConstraintSpec(name="c", expression="x", relation=relation, upper=upper)],
    )


def test_constraint_relation_errors_are_reported_as_failures() -> None:
    between = core.validate_model(_constrained_relation("between"))
    assert between["status"] == "FAIL"
    assert "requires upper" in between["scientific_constraints"][0]["detail"]
    assert between["repair_requires_approval"] is True

    unknown = core.validate_model(_constrained_relation("xx"))
    assert unknown["status"] == "FAIL"
    assert "unsupported constraint relation" in unknown["scientific_constraints"][0]["detail"]


def test_unit_engine_import_failure_is_unverified(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "axiomize.validation.dimensions", None)
    validation = core.validate_model(_ode_model())
    unit_checks = [c for c in validation["checks"] if c["name"] == "unit_engine"]
    assert len(unit_checks) == 1
    assert unit_checks[0]["status"] == "UNVERIFIED"


def test_causal_guard_ignores_non_dict_evidence() -> None:
    model = _model({
        "name": "causal-guard",
        "family": "causal",
        "variables": [{"name": "y", "role": "output", "initial": 0.0}],
        "equations": [{"target": "y", "expression": "y", "kind": "algebraic"}],
        "metadata": {"causal_identification": []},
    })
    validation = core.validate_model(model)
    guard = [c for c in validation["checks"] if c["name"] == "causal_identification"]
    assert guard[0]["status"] == "UNVERIFIED"
    assert "not identified" in guard[0]["detail"]


def test_residual_diagnostics_validation_and_lag_fallback() -> None:
    with pytest.raises(ValueError, match="shape mismatch"):
        core.residual_diagnostics(np.array([[1.0], [2.0]]), np.array([1.0, 2.0]))
    with pytest.raises(ValueError, match="require observations"):
        core.residual_diagnostics(np.array([]), np.array([]))
    with np.errstate(invalid="ignore", divide="ignore"):
        out = core.residual_diagnostics(np.array([0.0, 1.0, 2.0]), np.array([-1.0, 0.0, 0.0]))
    assert out["lag1_autocorrelation"] == 0.0
    assert out["rmse"] == pytest.approx(math.sqrt(2.0))


def test_fit_rejects_non_ode_models() -> None:
    model = _model({
        "name": "algebraic-fit",
        "family": "algebraic",
        "variables": [{"name": "y", "role": "output", "initial": 1.0}],
        "parameters": [{"name": "k", "value": 1.0, "fit": True}],
        "equations": [{"target": "y", "expression": "k", "kind": "algebraic"}],
    })
    out = core.fit_ode_model(model, time=[0.0, 0.5, 1.0], observations={"y": [1.0, 1.0, 1.0]})
    assert out["status"] == "TOOL_ROUTE_REQUIRED"


def test_fit_requires_approval_for_large_timeseries() -> None:
    time = np.linspace(0.0, 5.0, 170_000).tolist()
    out = core.fit_ode_model(_ode_model(fit=True), time=time, observations={})
    assert out["status"] == "APPROVAL_REQUIRED"
    assert out["cost"]["level"] == "high"


def test_fit_validation_errors() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        core.fit_ode_model(_ode_model(fit=True), time=[0.0, 0.0, 1.0],
                           observations={"x": [1.0, 1.0, 1.0]})
    with pytest.raises(ValueError, match="mark at least one parameter"):
        core.fit_ode_model(_ode_model(fit=False), time=[0.0, 0.5, 1.0],
                           observations={"x": [1.0, 1.0, 1.0]})
    with pytest.raises(ValueError, match="length must match time"):
        core.fit_ode_model(_ode_model(fit=True), time=[0.0, 0.5, 1.0],
                           observations={"x": [1.0, 1.0]})
    with pytest.raises(ValueError, match="unknown states"):
        core.fit_ode_model(_ode_model(fit=True), time=[0.0, 0.5, 1.0],
                           observations={"z": [1.0, 1.0, 1.0]})
    with pytest.raises(ValueError, match="needs an initial value"):
        core.fit_ode_model(_ode_model(fit=True, value=None), time=[0.0, 0.5, 1.0],
                           observations={"x": [1.0, 1.0, 1.0]})


def test_fit_reports_simulation_failure(monkeypatch) -> None:
    def failed_solve(*args, **kwargs):
        return type("Solution", (), {
            "success": False, "message": "forced failure", "y": np.zeros((1, 3)),
        })()

    monkeypatch.setattr(scipy.integrate, "solve_ivp", failed_solve)
    with pytest.raises(RuntimeError, match="ODE simulation failed during fitting"):
        core.fit_ode_model(_ode_model(fit=True), time=[0.0, 0.5, 1.0],
                           observations={"x": [1.0, 1.0, 1.0]})


def test_fit_success_and_singular_covariance(monkeypatch) -> None:
    time = [0.0, 0.5, 1.0, 1.5, 2.0]
    observations = {"x": [math.exp(-value) for value in time]}
    out = core.fit_ode_model(_ode_model(fit=True), time=time, observations=observations)
    assert out["status"] == "PASS"
    assert out["parameters"]["k"] == pytest.approx(1.0, abs=1e-5)
    assert out["identifiability"]["identifiable"] is True
    assert out["stderr"]["k"] is not None
    assert out["residual_diagnostics"]["x"]["rmse"] < 1e-5

    def singular_inverse(matrix):
        raise np.linalg.LinAlgError("forced singular covariance")

    monkeypatch.setattr(np.linalg, "inv", singular_inverse)
    degraded = core.fit_ode_model(_ode_model(fit=True), time=time, observations=observations)
    assert degraded["covariance"] is None
    assert degraded["identifiability"]["identifiable"] is False
    assert degraded["stderr"]["k"] is None


def test_rank_model_fits_rejects_unknown_criterion() -> None:
    with pytest.raises(ValueError, match="criterion must be aic, bic, or sse"):
        core.rank_model_fits({}, criterion="rmse")


def test_local_stability_requires_ode_model() -> None:
    model = _model({
        "name": "algebraic-stability",
        "family": "algebraic",
        "variables": [{"name": "y", "role": "output", "initial": 1.0}],
        "equations": [{"target": "y", "expression": "y", "kind": "algebraic"}],
    })
    with pytest.raises(ValueError, match="requires an ODE model"):
        core.local_stability(model, state={"y": 1.0})


def test_nondimensionalization_uses_bounds_for_scale() -> None:
    model = _model({
        "name": "scaling",
        "family": "ode",
        "variables": [{"name": "x", "initial": -5.0, "bounds": [-10.0, 10.0]}],
        "parameters": [{"name": "k", "value": 2.0}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    })
    plan = core.nondimensionalization_plan(model)
    assert plan["variable_scales"]["x"] == 10.0
    assert plan["parameter_scales"]["k"] == 2.0
    assert plan["applied"] is False


def test_discover_sparse_dynamics_validation_and_recovery() -> None:
    with pytest.raises(ValueError, match="same-length increasing"):
        core.discover_sparse_dynamics(time=[0.0, 1.0], state=[1.0], approve_heavy=True)
    time = np.linspace(0.0, 2.0, 50).tolist()
    state = np.exp(-np.asarray(time)).tolist()
    with pytest.raises(ValueError, match="degree must be between 1 and 5"):
        core.discover_sparse_dynamics(time=time, state=state, degree=0, approve_heavy=True)
    out = core.discover_sparse_dynamics(
        time=time, state=state, degree=2, threshold=1e-3, approve_heavy=True,
    )
    assert out["status"] == "PASS"
    terms = {row["term"]: row["coefficient"] for row in out["candidate_terms"]}
    assert terms["x"] == pytest.approx(-1.0, abs=0.05)
    assert out["rmse_derivative"] < 0.05

    empty = core.discover_sparse_dynamics(
        time=time, state=state, degree=1, threshold=1e9, approve_heavy=True,
    )
    assert empty["status"] == "PASS"
    assert empty["candidate_terms"] == []


def test_provenance_snapshot_handles_import_failure(monkeypatch) -> None:
    monkeypatch.setattr(core, "_module_present", lambda name: True)
    monkeypatch.setitem(sys.modules, "z3", None)
    snapshot = core.provenance_snapshot(_ode_model(), seed=4, data_hash="abc")
    assert snapshot["tool_versions"]["z3"] == "available"
    assert snapshot["seed"] == 4
    assert snapshot["data_hash"] == "abc"


def test_export_yaml_unavailable_and_available(monkeypatch) -> None:
    model = _ode_model()
    monkeypatch.setattr(core, "_module_present", lambda name: False)
    unavailable = core.export_model(model, format="yaml")
    assert unavailable["status"] == "TOOL_UNAVAILABLE"

    fake = types.ModuleType("yaml")
    fake.safe_dump = lambda payload, sort_keys=False: "name: ode-coverage"
    monkeypatch.setattr(core, "_module_present", lambda name: True)
    monkeypatch.setitem(sys.modules, "yaml", fake)
    available = core.export_model(model, format="yaml")
    assert available == {"format": "yaml", "content": "name: ode-coverage"}


def test_export_rejects_unknown_format() -> None:
    with pytest.raises(ValueError, match="format must be json, python, yaml, sbml, or cellml"):
        core.export_model(_ode_model(), format="xml")
