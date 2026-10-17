"""Secondary dimensional evaluator independently rejects ASTs if the first guard fails."""

from __future__ import annotations

import ast
from types import SimpleNamespace

import pytest

from axiomize import dimensional_engine as de


@pytest.mark.parametrize(
    ("expression", "dimensions", "message"),
    [
        ("undefined", {"x": {"L": 1.0}}, "unknown symbol"),
        ("4//2", {}, "unsupported operator"),
        ("eval(x)", {"x": {"L": 1.0}}, "unsupported function"),
    ],
)
def test_second_dimension_gate_does_not_trust_bypassed_ast_validator(monkeypatch, expression, dimensions, message):
    # Controlled fault injection deliberately disables the first-line AST policy.
    # The downstream dimensional interpreter must independently fail closed.
    monkeypatch.setattr(
        de,
        "validate_expression",
        lambda source, **_kwargs: ast.parse(source, mode="eval"),
    )
    with pytest.raises(ValueError, match=message):
        de._parse_dimension(expression, dimensions)


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {"symbol_units": [], "bayesian": []},
        {"bayesian": {"data": []}},
    ],
)
def test_malformed_advanced_metadata_does_not_create_unobserved_symbols(metadata):
    model = SimpleNamespace(
        family=SimpleNamespace(value="bayesian"),
        variables=[],
        metadata=metadata,
    )
    dims = {}
    units = {}
    de._register_advanced_symbols(model, dims, units)
    assert dims == {}
    assert units == {}


def test_bayesian_malformed_data_unit_mapping_defaults_to_explicit_dimensionless():
    model = SimpleNamespace(
        family=SimpleNamespace(value="bayesian"),
        variables=[],
        metadata={"bayesian": {"data": {"observed": [1, 2]}, "data_units": []}},
    )
    dims = {}
    units = {}
    de._register_advanced_symbols(model, dims, units)
    assert dims["observed"] == {}
    assert units["observed"] == "dimensionless"
