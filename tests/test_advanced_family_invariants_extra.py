"""Security and scientific invariants in native advanced-family helpers."""

from __future__ import annotations

import numpy as np
import pytest

from axiomize.advanced_family_engine import (
    _boundary_spec,
    _compile_expression,
    _compile_local_vector_field,
    _finalize,
    _flatten_validation_proxy,
    _parameter_values,
    _resolve_scalar,
)
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, ParameterSpec, VariableSpec


def _model(*, params=(), equations=(), variables=(), boundaries=None):
    return ModelIR(
        name="explicit-only",
        domain="biology",
        family=ModelFamily.PDE,
        variables=list(variables),
        parameters=list(params),
        equations=list(equations),
        boundary_conditions=boundaries or {},
    )


@pytest.mark.parametrize(
    ("expression", "rejected"),
    [
        ("unknown + 1", "unknown symbol"),
        ("sin(x).__class__", "unsupported expression syntax"),
        ("__import__('os')", "only approved"),
        ("sum([x])", "only approved"),
        ("x[0]", "unsupported expression syntax"),
        ("x if x>0 else 0", "unsupported expression syntax"),
    ],
)
def test_symbolic_expression_parser_refuses_nonmath_and_unknown_symbols(expression: str, rejected: str) -> None:
    with pytest.raises(ValueError, match=rejected):
        _compile_expression(expression, ["x"])


def test_explicit_expression_evaluates_sine_and_affine_equation() -> None:
    fn = _compile_expression("sin(x) + 2*x", ["x"])
    assert float(fn(0.0)) == pytest.approx(0.0)
    assert float(fn(np.pi / 2)) == pytest.approx(1 + np.pi)


@pytest.mark.parametrize(
    ("parameter", "override", "error"),
    [
        (ParameterSpec("gain", 0.3, bounds=(0.0, 1.0)), {"unknown": 0.5}, "unknown parameter"),
        (ParameterSpec("gain", None), {}, "has no value"),
        (ParameterSpec("gain", 0.3, bounds=(0.4, 0.5)), {}, "below lower"),
        (ParameterSpec("gain", 0.8, bounds=(0.4, 0.5)), {}, "above upper"),
        (ParameterSpec("gain", 0.3, bounds=(0.0, 1.0)), {"gain": -1}, "below lower"),
    ],
)
def test_parameter_resolution_rejects_unsupported_values(parameter, override, error):
    with pytest.raises(ValueError, match=error):
        _parameter_values(_model(params=[parameter]), override)


def test_parameter_override_and_scalar_reference_agree() -> None:
    model = _model(params=[ParameterSpec("gain", 0.3, bounds=(0.0, 1.0))])
    values = _parameter_values(model, {"gain": 0.9})
    assert values == {"gain": 0.9}
    assert _resolve_scalar("gain", values, name="rate") == pytest.approx(0.9)
    assert _resolve_scalar(4, values, name="rate") == pytest.approx(4)
    with pytest.raises(ValueError, match="unknown parameter"):
        _resolve_scalar("not_set", values, name="rate")


@pytest.mark.parametrize(
    "input_value",
    [
        {"time": [], "states": {"x": [[1, 2]]}},
        {"time": [0], "states": {}},
        {"time": [0, 1], "states": {"x": [1]}},
        {"time": [0, 1], "states": {"x": [[[1]], [[2]]]}},
        {"time": [0, 1], "states": {"x": [[1, 2], [3, 4]], "y": [[0], [1]]}},
    ],
)
def test_flattening_never_invents_missing_shapes(input_value):
    assert _flatten_validation_proxy(input_value) is input_value


def test_spatial_validation_propagates_time_and_state_axes_together() -> None:
    original = {
        "status": "PASS",
        "time": [0.0, 1.0],
        "states": {
            "x": [[1.0, 2.0], [3.0, 4.0]],
            "y": [[9.0, 8.0], [7.0, 6.0]],
        },
    }
    proxy = _flatten_validation_proxy(original)
    assert proxy["time"] == [0.0, 0.0, 1.0, 1.0]
    assert proxy["states"]["x"] == [1.0, 2.0, 3.0, 4.0]
    assert proxy["states"]["y"] == [9.0, 8.0, 7.0, 6.0]
    assert original["time"] == [0.0, 1.0]  # Never mutate evidence.


def test_finalization_fails_closed_when_constraint_validation_raises():
    model = _model()
    result = {"status": "PASS", "time": [0], "states": {"x": [1]}}

    def broken(*args, **kwargs):
        raise RuntimeError("validator failed")

    final = _finalize(model, result, broken)
    assert final["status"] == "FAIL"
    assert final["validation"]["status"] == "FAIL"
    assert "RuntimeError" in final["validation"]["checks"][0]["detail"]


def test_finalization_never_upgrades_fail_or_unknown_result():
    model = _model()

    def must_not_run(*args, **kwargs):
        raise AssertionError("validate must not run")

    value = {"status": "INCONCLUSIVE"}
    assert _finalize(model, value, must_not_run) is value


def test_validation_rejection_flows_to_final_status():
    model = _model()
    final = _finalize(model, {"status": "PASS"}, lambda *_args, **_kwargs: {"status": "FAIL"})
    assert final["status"] == "FAIL"


def test_local_state_vector_field_rejects_missing_equations():
    model = _model(variables=[VariableSpec("x", role="state")])
    with pytest.raises(ValueError, match="missing derivative equations"):
        _compile_local_vector_field(model, {})


def test_local_vector_field_matches_declared_rhs_scalar_and_vector():
    model = _model(
        variables=[VariableSpec("x", role="state")],
        params=[ParameterSpec("growth", 0.3)],
        equations=[EquationSpec("x", "growth*x")],
    )
    names, rhs = _compile_local_vector_field(model, {"growth": 0.3})
    assert names == ["x"]
    np.testing.assert_allclose(rhs(0, np.array([2.0])), [[0.6]])
    np.testing.assert_allclose(rhs(0, np.array([[2.0, 4.0]])), [[0.6, 1.2]])


def test_scalar_derivative_broadcasts_to_all_mesh_nodes():
    model = _model(
        variables=[VariableSpec("x", role="state")],
        equations=[EquationSpec("x", "2")],
    )
    _, rhs = _compile_local_vector_field(model, {})
    np.testing.assert_allclose(rhs(1, np.array([[2.0, 4.0, 6.0]])), [[2.0, 2.0, 2.0]])


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({"boundary_conditions": "invalid"}, {}),
        ({"boundary_conditions": {"x": {"left": 0}, "y": {"left": 10}}}, {"left": 0}),
        ({"boundary_conditions": {"left": 1, "right": 2}}, {"left": 1, "right": 2}),
        ({"boundary_conditions": {"another": 10}}, {}),
    ],
)
def test_boundary_selection_never_invents_missing_constraints(config, expected):
    assert _boundary_spec(_model(), config, "x") == expected
