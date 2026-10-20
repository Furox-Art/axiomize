"""Round-2 coverage hardening for ``axiomize.tools.autodiff.jax_tool``.

JAX is an optional dependency that is not installed in the coverage environment.
The tests install a fake ``jax`` package at the import boundary (with real
``numpy`` behind ``jax.numpy``) and then execute the real ``JAXTool`` code so the
gradient/Jacobian/Hessian wiring is exercised and asserted against analytic
derivatives.
"""
from __future__ import annotations

import sys
import types
from typing import Any

import numpy as np
import pytest

from axiomize.tools.autodiff.jax_tool import JAXTool, _to_native


def _central_gradient(f: Any, x: Any) -> Any:
    arr = np.asarray(x, dtype=float)
    h = 1e-6
    if arr.ndim == 0:
        value = float(arr)
        return (f(value + h) - f(value - h)) / (2.0 * h)
    partials = []
    for index in range(arr.size):
        step = np.zeros_like(arr)
        step.flat[index] = h
        partials.append((f(arr + step) - f(arr - step)) / (2.0 * h))
    return np.asarray(partials).reshape(arr.shape)


def _central_hessian(f: Any, x: Any) -> Any:
    value = float(x)
    h = 1e-4
    return (f(value + h) - 2.0 * f(value) + f(value - h)) / (h * h)


def _install_fake_jax(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    jax = types.ModuleType("jax")
    jax.__version__ = "0.4.99"
    jax.numpy = np
    jax.grad = lambda f: (lambda x: _central_gradient(f, x))
    jax.jacfwd = lambda f: (lambda x: np.asarray(_central_gradient(f, x)))
    jax.hessian = lambda f: (lambda x: _central_hessian(f, x))
    monkeypatch.setitem(sys.modules, "jax", jax)
    monkeypatch.setitem(sys.modules, "jax.numpy", np)
    return jax


def test_probe_version_reads_the_installed_jax_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_jax(monkeypatch)
    assert JAXTool._probe_version() == "0.4.99"
    meta = JAXTool.availability()
    assert meta.available is True
    assert meta.version == "0.4.99"


def test_grad_executes_real_jax_wiring(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_jax(monkeypatch)
    result = JAXTool().execute({"operation": "grad", "x": 2.0, "function": "x**2"})
    assert result["status"] == "PASS"
    assert result["operation"] == "grad"
    assert result["backend"] == "jax-0.4.99"
    assert result["x"] == 2.0
    assert result["function"] == "x**2"
    assert result["gradient"] == pytest.approx(4.0, rel=1e-5)


def test_grad_supports_vector_input(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_jax(monkeypatch)
    result = JAXTool().execute({"operation": "grad", "x": [1.0, 2.0, 3.0], "function": "x**2"})
    assert result["status"] == "PASS"
    assert result["x"] == [1.0, 2.0, 3.0]
    assert result["gradient"] == pytest.approx([2.0, 4.0, 6.0], rel=1e-5)


def test_jacobian_executes_real_jax_wiring(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_jax(monkeypatch)
    result = JAXTool().execute({"operation": "jacobian", "x": [1.0, 2.0], "function": "x**2"})
    assert result["status"] == "PASS"
    assert result["operation"] == "jacobian"
    assert result["backend"] == "jax-0.4.99"
    assert result["x"] == [1.0, 2.0]
    assert result["jacobian"] == pytest.approx([2.0, 4.0], rel=1e-5)


def test_hessian_executes_real_jax_wiring(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_jax(monkeypatch)
    result = JAXTool().execute({"operation": "hessian", "x": 3.0, "function": "x**2"})
    assert result["status"] == "PASS"
    assert result["operation"] == "hessian"
    assert result["backend"] == "jax-0.4.99"
    assert result["x"] == 3.0
    assert result["hessian"] == pytest.approx(2.0, rel=1e-3)


def test_to_native_converts_scalars_and_arrays() -> None:
    assert _to_native(np.float64(1.25)) == pytest.approx(1.25)
    assert _to_native(np.array([1.0, 2.0])) == [1.0, 2.0]


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ([], "payload must be an object"),
        ({"operation": "laplacian", "x": 1.0}, "operation must be"),
        ({"operation": "grad"}, "needs 'x'"),
        ({"operation": "grad", "x": True}, "must not be boolean"),
        ({"operation": "grad", "x": []}, "must not be empty"),
        ({"operation": "grad", "x": object()}, "number or list of numbers"),
        ({"operation": "grad", "x": [1.0, "bad"]}, "could not convert"),
    ],
)
def test_validate_input_rejects_malformed_requests(payload: Any, match: str) -> None:
    with pytest.raises((ValueError, TypeError), match=match):
        JAXTool().validate_input(payload)


def test_expression_must_depend_on_x_only() -> None:
    with pytest.raises(ValueError, match="must depend on x only"):
        JAXTool().execute({"operation": "grad", "x": 1.0, "function": "y**2"})


def test_unavailable_jax_is_reported_as_tool_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiomize.tools.base import ToolMetadata

    unavailable = ToolMetadata(name="jax", available=False, reason="No module named 'jax'")
    monkeypatch.setattr(JAXTool, "availability", classmethod(lambda cls: unavailable))
    with pytest.raises(RuntimeError, match="TOOL_UNAVAILABLE: jax is not installed"):
        JAXTool().execute({"operation": "grad", "x": 1.0, "function": "x**2"})
