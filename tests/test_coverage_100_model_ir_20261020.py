"""Coverage-completing tests for Model IR validation and legacy migration."""

from __future__ import annotations

import pytest

from axiomize.model_ir import (
    ConstraintSpec,
    EquationSpec,
    ModelFamily,
    ModelIR,
    ParameterSpec,
    ProvenanceEvent,
    SolverSpec,
    VariableSpec,
    migrate_payload,
)


def _payload(**overrides):
    payload = {
        "schema_version": "1.0",
        "name": "ir-coverage",
        "domain": "general",
        "family": "ode",
        "variables": [{"name": "x", "initial": 1.0}],
        "parameters": [],
        "equations": [{"target": "x", "expression": "0", "kind": "derivative"}],
    }
    payload.update(overrides)
    return payload


def test_bounds_and_bounded_list_validation() -> None:
    with pytest.raises(ValueError, match="bounds must have length 2"):
        VariableSpec.from_dict({"name": "x", "bounds": [0.0]})
    with pytest.raises(ValueError, match="lower bound must be <= upper bound"):
        VariableSpec.from_dict({"name": "x", "bounds": [2.0, 1.0]})

    with pytest.raises(ValueError, match="invalid Model IR structure"):
        ModelIR.from_dict(_payload(variables=None))
    with pytest.raises(ValueError, match="variables must be an array"):
        ModelIR.from_dict(_payload(variables="x"))
    with pytest.raises(ValueError, match="exceeds hard safety limit"):
        ModelIR.from_dict(_payload(variables=[{"name": "x"}] * 1_001))


def test_family_aliases_and_unknown_family() -> None:
    assert ModelFamily.parse("sde") is ModelFamily.STOCHASTIC
    assert ModelFamily.parse("abm") is ModelFamily.AGENT_BASED
    assert ModelFamily.parse("differential-algebraic") is ModelFamily.DAE
    with pytest.raises(ValueError, match="unsupported model family"):
        ModelFamily.parse("nope")


def test_variable_and_parameter_entry_validation() -> None:
    with pytest.raises(ValueError, match="variable entry must be an object"):
        VariableSpec.from_dict(5)
    with pytest.raises(ValueError, match="unsupported role"):
        VariableSpec.from_dict({"name": "x", "role": "wizard"})
    with pytest.raises(ValueError, match="parameter entry must be an object"):
        ParameterSpec.from_dict(5)
    with pytest.raises(ValueError, match="prior must be an object"):
        ParameterSpec.from_dict({"name": "k", "prior": []})


def test_equation_entry_validation() -> None:
    with pytest.raises(ValueError, match="equation entry must be an object"):
        EquationSpec.from_dict(5)
    with pytest.raises(ValueError, match="expression must be non-empty"):
        EquationSpec.from_dict({"target": "x", "expression": " "})
    with pytest.raises(ValueError, match="unsupported equation kind"):
        EquationSpec.from_dict({"target": "x", "expression": "0", "kind": "magic"})
    with pytest.raises(ValueError, match="requires a target"):
        EquationSpec.from_dict({"target": "", "expression": "0", "kind": "derivative"})


def test_constraint_entry_validation() -> None:
    with pytest.raises(ValueError, match="constraint entry must be an object"):
        ConstraintSpec.from_dict(5)
    with pytest.raises(ValueError, match="unsupported constraint relation"):
        ConstraintSpec.from_dict({"name": "c", "expression": "x", "relation": "gt"})
    with pytest.raises(ValueError, match="unsupported constraint severity"):
        ConstraintSpec.from_dict({"name": "c", "expression": "x", "severity": "fatal"})
    with pytest.raises(ValueError, match="tolerance must be non-negative"):
        ConstraintSpec.from_dict({"name": "c", "expression": "x", "tolerance": -1.0})
    with pytest.raises(ValueError, match="'between' requires upper"):
        ConstraintSpec.from_dict({"name": "c", "expression": "x", "relation": "between"})
    with pytest.raises(ValueError, match="upper must be >= threshold"):
        ConstraintSpec.from_dict({
            "name": "c", "expression": "x", "relation": "between",
            "threshold": 1.0, "upper": 0.5,
        })
    with pytest.raises(ValueError, match="expression must be non-empty"):
        ConstraintSpec.from_dict({"name": "c", "expression": " "})


def test_solver_and_provenance_entry_validation() -> None:
    with pytest.raises(ValueError, match="solver must be an object"):
        SolverSpec.from_dict(5)
    with pytest.raises(ValueError, match="rtol and atol must be positive"):
        SolverSpec.from_dict({"rtol": 0.0})
    with pytest.raises(ValueError, match="fallbacks must be an array"):
        SolverSpec.from_dict({"fallbacks": list(range(33))})
    with pytest.raises(ValueError, match="provenance event must be an object"):
        ProvenanceEvent.from_dict(5)
    with pytest.raises(ValueError, match="provenance detail must be an object"):
        ProvenanceEvent.from_dict({"action": "a", "detail": []})


def test_model_payload_container_validation() -> None:
    with pytest.raises(ValueError, match="Model IR must be an object"):
        ModelIR.from_dict(5)
    with pytest.raises(ValueError, match="boundary_conditions must be an object"):
        ModelIR.from_dict(_payload(boundary_conditions=[]))
    with pytest.raises(ValueError, match="validity_domain must be an object"):
        ModelIR.from_dict(_payload(validity_domain=[]))
    with pytest.raises(ValueError, match="metadata must be an object"):
        ModelIR.from_dict(_payload(metadata=[]))
    with pytest.raises(ValueError, match="provenance must be an array"):
        ModelIR.from_dict(_payload(provenance={}))
    with pytest.raises(ValueError, match="assumptions must be an array"):
        ModelIR.from_dict(_payload(assumptions={}))


def test_legacy_migration_accepts_state_lists_and_rejects_bad_rhs() -> None:
    migrated = ModelIR.from_dict({
        "schema_version": "0.9",
        "name": "legacy",
        "family": "ode",
        "states": [{"name": "x", "initial": 1.0}],
        "rhs": {"x": "0"},
    }, allow_migration=True)
    assert [v.name for v in migrated.variables] == ["x"]
    assert migrated.equations[0].kind == "derivative"

    with pytest.raises(ValueError, match="legacy rhs must be a mapping"):
        ModelIR.from_dict({
            "schema_version": "0.9",
            "name": "legacy-bad",
            "family": "ode",
            "states": {"x": 1.0},
            "rhs": [],
        }, allow_migration=True)

    preview = migrate_payload({
        "schema_version": "0.9",
        "name": "legacy-preview",
        "family": "ode",
        "states": {"x": 1.0},
        "rhs": {"x": "0"},
    }, allow_migration=True)
    assert preview["variables"] == [{"name": "x", "initial": 1.0}]
