"""Versioned Model IR cannot silently repair or reinterpret missing science."""

from __future__ import annotations

import copy

import pytest

from axiomize.model_ir import (
    MigrationApprovalRequired,
    ModelFamily,
    ModelIR,
    ProvenanceEvent,
    SolverSpec,
    UnsupportedSchemaVersion,
    migrate_payload,
    migration_preview,
)


@pytest.fixture
def valid_ir():
    return {
        "schema_version": "1.0",
        "name": "scientific",
        "domain": "physics",
        "family": "ode",
        "variables": [{"name": "x", "initial": 1.0, "bounds": [0.0, 2.0]}],
        "parameters": [{"name": "rate", "value": 0.2, "bounds": [0.0, 1.0]}],
        "equations": [{"target": "x", "kind": "derivative", "expression": "-rate*x"}],
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", " ", "invalid Model IR structure"),
        ("variables", [], "invalid Model IR structure"),
        ("equations", [], "invalid Model IR structure"),
        ("variables", [{"name": "x"}, {"name": "x"}], "unique_variables"),
        ("parameters", [{"name": "rate"}, {"name": "rate"}], "unique_parameters"),
        ("parameters", [{"name": "x", "value": 1.0}], "symbol_namespace"),
        ("independent_variable", "x", "independent_namespace"),
        ("equations", [{"target": "unknown", "kind": "derivative", "expression": "1"}], "equation_targets_known"),
        (
            "equations",
            [
                {"target": "x", "kind": "derivative", "expression": "1"},
                {"target": "x", "kind": "derivative", "expression": "2"},
            ],
            "unique_derivative_targets",
        ),
        ("variables", [{"name": "x", "initial": -1.0, "bounds": [0.0, 1.0]}], "initial_in_bounds"),
        ("parameters", [{"name": "rate", "value": 2.0, "bounds": [0.0, 1.0]}], "parameter_in_bounds"),
        ("boundary_conditions", [], "boundary_conditions must be an object"),
        ("validity_domain", [], "validity_domain must be an object"),
        ("metadata", [], "metadata must be an object"),
        ("assumptions", {}, "assumptions must be an array"),
        ("provenance", {}, "provenance must be an array"),
        ("solver", [], "solver must be an object"),
    ],
)
def test_model_ir_refuses_invalid_structure_instead_of_fabricating_evidence(valid_ir, field, value, message):
    doc = {**valid_ir, field: value}
    with pytest.raises(ValueError, match=message):
        ModelIR.from_dict(doc)


@pytest.mark.parametrize(
    ("field", "item", "message"),
    [
        ("variables", {"name": "a", "role": "not-a-role"}, "unsupported role"),
        ("variables", {"name": "a", "initial": float("nan")}, "must be finite"),
        ("variables", {"name": "a", "bounds": [2.0, 1.0]}, "lower bound"),
        ("variables", {"name": "a", "bounds": [0.0]}, "length 2"),
        ("parameters", {"name": "rate", "prior": []}, "prior must be an object"),
        ("parameters", {"name": "rate", "value": float("inf")}, "must be finite"),
        ("equations", {"target": "x", "expression": ""}, "non-empty"),
        ("equations", {"target": "x", "expression": "x", "kind": "fiction"}, "unsupported equation kind"),
        ("equations", {"expression": "x", "kind": "algebraic"}, "requires a target"),
        ("constraints", {"name": "positive", "expression": "x", "relation": "bad"}, "unsupported constraint relation"),
        ("constraints", {"name": "positive", "expression": "x", "severity": "bad"}, "unsupported constraint severity"),
        ("constraints", {"name": "positive", "expression": "x", "tolerance": -0.1}, "non-negative"),
        ("constraints", {"name": "positive", "expression": "x", "relation": "between"}, "requires upper"),
        (
            "constraints",
            {"name": "positive", "expression": "x", "relation": "between", "upper": -1.0},
            "upper must be >=",
        ),
    ],
)
def test_nested_scientific_contracts_reject_unbounded_or_missing_semantics(valid_ir, field, item, message):
    document = copy.deepcopy(valid_ir)
    document[field] = [item] if field != "constraints" else [item]
    if field == "variables":
        document["variables"] = [item]
    with pytest.raises(ValueError, match=message):
        ModelIR.from_dict(document)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"rtol": 0}, "must be positive"),
        ({"atol": -1.0}, "must be positive"),
        ({"max_steps": 0}, "positive integer"),
        ({"max_steps": 1.5}, "positive integer"),
        ({"max_steps": True}, "positive integer"),
        ({"max_steps": float("nan")}, "must be finite"),
        ({"fallbacks": "bad"}, "fallbacks must be an array"),
        ({"fallbacks": ["solver"] * 33}, "fallbacks must be an array"),
    ],
)
def test_solver_config_never_assumes_invalid_tolerances_legal(payload, message):
    with pytest.raises(ValueError, match=message):
        SolverSpec.from_dict(payload)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("sde", ModelFamily.STOCHASTIC),
        ("abm", ModelFamily.AGENT_BASED),
        ("des", ModelFamily.DISCRETE_EVENT),
        ("differential-algebraic", ModelFamily.DAE),
        ("multi_physics", ModelFamily.MULTIPHYSICS),
        ("coupled_physics", ModelFamily.MULTIPHYSICS),
    ],
)
def test_named_model_families_are_canonical_not_guessed(name, expected):
    assert ModelFamily.parse(name) is expected


def test_unknown_model_family_rejected_not_silently_routed():
    with pytest.raises(ValueError, match="unsupported model family"):
        ModelFamily.parse("random-model")


def test_ir_roundtrip_keeps_scientific_parameters_and_source_version(valid_ir):
    model = ModelIR.from_dict(valid_ir)
    assert ModelIR.from_dict(model.to_dict()).to_dict() == model.to_dict()
    assert model.schema_version == "1.0"


def test_legacy_migration_requires_approval_and_records_provenance():
    legacy = {
        "schema_version": "0.9",
        "name": "old",
        "domain": "physics",
        "model_family": "ode",
        "states": {"x": 1.0},
        "rhs": {"x": "-x"},
    }
    plan = migration_preview(legacy)
    assert plan["required"] is True
    assert plan["supported"] is True
    with pytest.raises(MigrationApprovalRequired):
        ModelIR.from_dict(legacy)
    migrated = ModelIR.from_dict(legacy, allow_migration=True)
    assert migrated.family is ModelFamily.ODE
    assert migrated.provenance[-1].action == "model_ir_migration"
    assert migrated.metadata["migration_history"][-1] == plan
    assert legacy["schema_version"] == "0.9"


def test_unsupported_future_schema_never_claims_migration_is_safe(valid_ir):
    valid_ir["schema_version"] = "4.0"
    plan = migration_preview(valid_ir)
    assert plan["supported"] is False
    with pytest.raises(UnsupportedSchemaVersion):
        migrate_payload(valid_ir, allow_migration=True)


def test_legacy_migration_refuses_nondeterministic_rhs():
    with pytest.raises(ValueError, match="legacy rhs must be a mapping"):
        migrate_payload({"schema_version": "0.9", "rhs": ["x"]}, allow_migration=True)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"action": "test", "detail": {"sha": "123"}}, "123"),
        ({"action": "test"}, None),
    ],
)
def test_provenance_event_is_structural_and_explicit(value, expected):
    event = ProvenanceEvent.from_dict(value)
    assert event.action == "test"
    assert event.detail.get("sha") == expected


def test_invalid_provenance_detail_refused():
    with pytest.raises(ValueError, match="detail must be an object"):
        ProvenanceEvent.from_dict({"action": "x", "detail": []})
