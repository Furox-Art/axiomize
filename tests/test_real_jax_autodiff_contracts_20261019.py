"""Real optional JAX numerical derivatives with explicit absence handling."""
from __future__ import annotations

import math

import pytest

from axiomize.tools.autodiff.jax_tool import JAXTool, _parsed_function, _to_native


@pytest.mark.parametrize("payload, error", [
    (None, "payload must be an object"),
    ([], "payload must be an object"),
    ({}, "payload needs"),
    ({"operation": "integrate", "x": 1.0}, "operation must"),
    ({"operation": "grad", "x": True}, "must not be boolean"),
    ({"operation": "grad", "x": "not-a-number"}, "number or list"),
    ({"operation": "grad", "x": []}, "must not be empty"),
    ({"operation": "grad", "x": ["invalid"]}, "could not convert"),
])
def test_invalid_payloads_fail_before_optional_import(payload, error):
    with pytest.raises(ValueError, match=error):
        JAXTool().validate_input(payload)


def test_metadata_reflects_real_backend_presence():
    meta = JAXTool.availability()
    assert meta.name == "jax"
    assert "grad" in meta.capabilities
    assert meta.version if meta.available else meta.reason


def test_expression_rejects_unknown_symbols_and_host_language_calls():
    with pytest.raises(ValueError, match="depend on x only"):
        _parsed_function("x+y")
    with pytest.raises(ValueError):
        JAXTool().execute({"x": 3.0, "function": "__import__(x)"})


@pytest.mark.parametrize("operation, key, answer", [
    ("grad", "gradient", 6.0),
    ("jacobian", "jacobian", 6.0),
    ("hessian", "hessian", 2.0),
])
def test_real_derivatives_or_explicit_tool_unavailable(operation, key, answer):
    tool = JAXTool()
    payload = {"operation": operation, "x": 3.0, "function": "x**2"}
    if not tool.availability().available:
        with pytest.raises(RuntimeError, match="TOOL_UNAVAILABLE"):
            tool.execute(payload)
        return
    result = tool.execute(payload)
    assert result["status"] == "PASS"
    assert result["backend"].startswith("jax-")
    assert result[key] == pytest.approx(answer, abs=1e-5)


def test_real_vector_autodiff_or_explicit_unavailable():
    tool = JAXTool()
    payload = {"x": [1.0, 2.0, 3.0], "function": "x**2"}
    if not tool.availability().available:
        with pytest.raises(RuntimeError, match="TOOL_UNAVAILABLE"):
            tool.execute(payload)
        return
    assert tool.execute(payload)["gradient"] == pytest.approx([2.0, 4.0, 6.0], abs=1e-5)


def test_tracer_conversion_is_standard_json_numeric():
    assert _to_native(1.5) == 1.5
    assert _to_native([1.0, 2.0]) == [1.0, 2.0]


def test_real_gradient_changes_with_observed_input():
    tool = JAXTool()
    if not tool.availability().available:
        with pytest.raises(RuntimeError, match="TOOL_UNAVAILABLE"):
            tool.execute({"x": 1.0})
        return
    first = tool.execute({"x": 1.0})["gradient"]
    second = tool.execute({"x": 2.0})["gradient"]
    assert math.isclose(first, 2.0)
    assert math.isclose(second, 4.0)
