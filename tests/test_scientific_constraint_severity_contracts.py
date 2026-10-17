"""Direct scientific constraint evaluation with visible severity and provenance."""

from __future__ import annotations

import pytest

from axiomize.general_engine_core import (
    _constraint_context,
    _evaluate_constraint,
    validate_model,
)
from axiomize.model_ir import ConstraintSpec, EquationSpec, ModelFamily, ModelIR, ParameterSpec, VariableSpec


def model(constraint=()):
    return ModelIR(
        name="experimental",
        domain="physics",
        family=ModelFamily.ODE,
        variables=[VariableSpec("x", initial=1.0)],
        parameters=[ParameterSpec("rate", 0.2)],
        equations=[EquationSpec("x", "-rate*x")],
        constraints=list(constraint),
    )


@pytest.mark.parametrize(
    ("relation", "threshold", "upper", "observed", "status"),
    [
        ("ge", 0.0, None, 1.0, "PASS"),
        ("ge", 2.0, None, 1.0, "FAIL"),
        ("le", 2.0, None, 1.0, "PASS"),
        ("le", 0.0, None, 1.0, "FAIL"),
        ("eq", 1.0, None, 1.0, "PASS"),
        ("eq", 2.0, None, 1.0, "FAIL"),
        ("between", 0.0, 2.0, 1.0, "PASS"),
        ("between", 1.5, 2.0, 1.0, "FAIL"),
        ("between", 0.0, 0.5, 1.0, "FAIL"),
    ],
)
def test_model_constraint_relations_measure_actual_margin(relation, threshold, upper, observed, status):
    spec = ConstraintSpec(
        name="physical",
        expression="x",
        relation=relation,
        threshold=threshold,
        upper=upper,
        tolerance=1e-10,
        scientific_basis="registered physical constraint",
    )
    output = _evaluate_constraint(spec, [{"x": observed}])
    assert output["status"] == status
    assert output["scientific_basis"] == "registered physical constraint"
    assert output["relation"] == relation
    assert "detail" in output


def test_constraint_is_checked_across_entire_trajectory_not_only_endpoint():
    spec = ConstraintSpec("physical", "x", relation="ge", threshold=0.5)
    trajectory = [{"x": 0.8}, {"x": 0.4}, {"x": 0.9}]
    result = _evaluate_constraint(spec, trajectory)
    assert result["status"] == "FAIL"
    assert "min_margin" in result["detail"]


def test_constraint_tolerance_does_not_silently_allow_large_violation():
    approximate = ConstraintSpec("near-zero", "x", relation="eq", threshold=0.0, tolerance=0.01)
    assert _evaluate_constraint(approximate, [{"x": 0.005}])["status"] == "PASS"
    assert _evaluate_constraint(approximate, [{"x": 0.05}])["status"] == "FAIL"


def test_invalid_nonfinite_constraint_input_fails_closed():
    spec = ConstraintSpec("finite", "x", relation="ge", threshold=0.0)
    out = _evaluate_constraint(spec, [{"x": float("nan")}])
    assert out["status"] == "FAIL"
    assert "non-finite" in out["detail"]


def test_between_constraint_without_upper_is_explicit_error():
    spec = ConstraintSpec("no-bound", "x", relation="between", threshold=0.0)
    with pytest.raises(ValueError, match="requires upper"):
        _evaluate_constraint(spec, [{"x": 1.0}])


def test_invalid_unsupported_relation_is_not_silently_reinterpreted():
    spec = ConstraintSpec("unsupported", "x", relation="not-real", threshold=0.0)
    with pytest.raises(ValueError, match="unsupported constraint relation"):
        _evaluate_constraint(spec, [{"x": 1.0}])


def test_constraint_context_without_simulation_uses_declared_initial_conditions():
    contexts = _constraint_context(model(), None)
    assert contexts == [{"rate": 0.2, "x": 1.0}]


def test_constraint_context_for_trajectory_carries_time_state_and_parameters():
    contexts = _constraint_context(
        model(), {"time": [0.0, 1.0], "states": {"x": [1.0, 0.8]}, "parameters": {"rate": 0.3}}
    )
    assert contexts == [
        {"t": 0.0, "rate": 0.3, "x": 1.0},
        {"t": 1.0, "rate": 0.3, "x": 0.8},
    ]


def test_constraint_context_with_static_state_uses_actual_not_initial_values():
    contexts = _constraint_context(model(), {"states": {"x": 0.25}})
    assert contexts == [{"rate": 0.2, "x": 0.25}]


@pytest.mark.parametrize(("severity", "expected"), [("error", "FAIL"), ("warning", "PASS"), ("info", "PASS")])
def test_warning_and_hard_scientific_constraint_violations_remain_distinct(severity, expected):
    spec = ConstraintSpec(
        "upper limit",
        "x",
        relation="le",
        threshold=0.5,
        scientific_basis="observed admissible upper limit",
        severity=severity,
    )
    validation = validate_model(model([spec]))
    assert validation["status"] == expected
    assert validation["scientific_constraints"][0]["status"] == "FAIL"
    assert validation["scientific_constraints"][0]["severity"] == severity
    assert validation["repair_requires_approval"] is True
    assert validation["repair_proposal"] is not None


def test_unidentified_causal_claim_is_marked_unverified():
    causal = model()
    causal.metadata["causal_claim"] = True
    result = validate_model(causal)
    claim = next(check for check in result["checks"] if check["name"] == "causal_identification")
    assert claim["status"] == "UNVERIFIED"
    assert result["status"] == "PASS"
