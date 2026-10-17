"""Model IR keeps exact provenance, explicit migration and no fabricated schema entries."""

from __future__ import annotations

import pytest

from axiomize.model_ir import (
    ConstraintSpec,
    EquationSpec,
    ModelIR,
    ParameterSpec,
    ProvenanceEvent,
    VariableSpec,
    _bounded_list,
    migrate_payload,
    migration_preview,
)


def test_missing_collection_is_empty_not_an_implicit_observation():
    assert _bounded_list(None, name="variables", maximum=4) == []


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({}, "must be an array"),
        ("not-array", "must be an array"),
        ([1, 2, 3, 4, 5], "exceeds hard safety limit"),
    ],
)
def test_schema_collection_counts_enforced_before_per_item_allocation(value, message):
    with pytest.raises(ValueError, match=message):
        _bounded_list(value, name="variables", maximum=4)


def test_model_ir_nonobject_root_is_rejected_not_migrated():
    with pytest.raises(ValueError, match="Model IR must be an object"):
        ModelIR.from_dict([])


@pytest.mark.parametrize(
    ("constructor", "message"),
    [
        (VariableSpec.from_dict, "variable entry must be an object"),
        (ParameterSpec.from_dict, "parameter entry must be an object"),
        (EquationSpec.from_dict, "equation entry must be an object"),
        (ConstraintSpec.from_dict, "constraint entry must be an object"),
        (ProvenanceEvent.from_dict, "provenance event must be an object"),
    ],
)
def test_scalar_instead_of_structured_model_element_is_refused(constructor, message):
    with pytest.raises(ValueError, match=message):
        constructor([])


@pytest.mark.parametrize(
    ("element", "message"),
    [
        ({"name": "x", "role": "secret"}, "unsupported role"),
        ({"name": "x", "initial": float("nan")}, "must be finite"),
        ({"name": "x", "bounds": [4.0, 3.0]}, "lower bound"),
    ],
)
def test_variable_requires_physical_metadata_and_consistent_bounds(element, message):
    with pytest.raises(ValueError, match=message):
        VariableSpec.from_dict(element)


@pytest.mark.parametrize(
    ("element", "message"),
    [
        ({"name": "k", "prior": []}, "prior must be an object"),
        ({"name": "k", "value": float("inf")}, "must be finite"),
    ],
)
def test_parameter_prior_must_be_explicit_and_finite(element, message):
    with pytest.raises(ValueError, match=message):
        ParameterSpec.from_dict(element)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"target": "x", "expression": ""}, "expression must be non-empty"),
        ({"expression": "x", "kind": "derivative"}, "requires a target"),
        ({"target": "x", "expression": "x", "kind": "unknown"}, "unsupported equation kind"),
    ],
)
def test_unresolved_equation_semantics_cannot_be_accepted_implicitly(payload, message):
    with pytest.raises(ValueError, match=message):
        EquationSpec.from_dict(payload)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"name": "positive", "expression": "", "relation": "ge"}, "expression must be non-empty"),
        ({"name": "range", "expression": "x", "relation": "between"}, "requires upper"),
        ({"name": "bad_tol", "expression": "x", "tolerance": -1}, "must be non-negative"),
        ({"name": "invalid_relation", "expression": "x", "relation": "unknown"}, "unsupported constraint relation"),
        ({"name": "invalid_severity", "expression": "x", "severity": "crucial"}, "unsupported constraint severity"),
    ],
)
def test_constraint_contract_refuses_unstated_bounds_or_nonvalid_relations(payload, message):
    with pytest.raises(ValueError, match=message):
        ConstraintSpec.from_dict(payload)


def test_unversioned_legacy_model_requires_actual_migration_approval():
    source = {"model_family": "algebraic", "states": {"x": 1.0}, "rhs": {"x": "-x"}}
    preview = migration_preview(source)
    assert preview["required"] is True
    assert preview["supported"] is True
    assert "rename states -> variables" in preview["changes"]
    assert "rename model_family -> family" in preview["changes"]
    converted = migrate_payload(source, allow_migration=True)
    assert converted["schema_version"] == "1.0"
    assert converted["family"] == "algebraic"
    assert converted["variables"][0] == {"name": "x", "initial": 1.0}
    assert converted["equations"][0]["expression"] == "-x"
    assert converted["provenance"][0]["action"] == "model_ir_migration"
    assert source == {"model_family": "algebraic", "states": {"x": 1.0}, "rhs": {"x": "-x"}}


def test_legacy_states_array_remains_array_under_approved_migration():
    source = {"schema_version": "0.9", "states": [{"name": "x"}], "family": "ode"}
    migrated = migrate_payload(source, allow_migration=True)
    assert migrated["variables"] == [{"name": "x"}]
    assert migrated["family"] == "ode"


def test_legacy_migration_does_not_override_explicit_new_schema_fields():
    source = {
        "schema_version": "0.9",
        "model_family": "algebraic",
        "family": "ode",
        "states": {"a": 1.0},
        "variables": [{"name": "b"}],
        "rhs": {"a": "1"},
        "equations": [{"target": "b", "expression": "1"}],
    }
    migrated = migrate_payload(source, allow_migration=True)
    assert migrated["family"] == "ode"
    assert migrated["variables"] == [{"name": "b"}]
    assert migrated["equations"] == [{"target": "b", "expression": "1"}]


def test_newer_unknown_schema_has_no_silent_migration():
    p = migration_preview({"schema_version": "2.5"})
    assert p["supported"] is False
    assert p["required"] is True
    with pytest.raises(ValueError, match="unsupported Model IR schema"):
        migrate_payload({"schema_version": "2.5"}, allow_migration=True)


def test_current_schema_has_no_change_or_unnecessary_migration_provenance():
    source = {"schema_version": "1.0", "family": "ode"}
    assert migration_preview(source)["required"] is False
    assert migrate_payload(source) == source


def test_valid_between_constraint_requires_and_preserves_ordered_numeric_bounds():
    value=ConstraintSpec.from_dict({
        "name":"valid interval", "expression":"x",
        "relation":"between", "threshold":1.,"upper":2.,
    })
    assert value.threshold==1.
    assert value.upper==2.
    assert value.relation=="between"
