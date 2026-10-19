"""JAX automatic differentiation backend (GAP-1).

Provides real gradient, Jacobian, and Hessian computation when JAX is
installed. Falls back to ``ToolMetadata(available=False)`` otherwise —
the native Metropolis-Hastings sampler and built-in finite differences
remain the honest always-present fallbacks.
"""

from __future__ import annotations

from typing import Any, ClassVar

from axiomize.safe_expression import auto_symbol_map, sympy_expression
from axiomize.tools.base import ScientificTool


def _parsed_function(function_expr: str) -> tuple[dict[str, Any], Any]:
    """Parse the tool's ``function`` argument through the hardened parser.

    Returns a symbol map that always contains ``x`` plus the SymPy
    expression. The text is never passed to ``sympy.sympify``: sympify
    *evaluates* its string argument, so a tool-supplied expression could
    execute arbitrary Python. Only a bounded arithmetic AST is accepted and
    it is translated directly to SymPy.
    """
    import sympy

    symbols = auto_symbol_map(function_expr)
    unexpected = sorted(set(symbols) - {"x"})
    if unexpected:
        raise ValueError(
            f"jax: function expression must depend on x only; got symbols: {unexpected}"
        )
    symbols.setdefault("x", sympy.Symbol("x", real=True))
    return symbols, sympy_expression(function_expr, symbols)


class JAXTool(ScientificTool):
    """Automatic differentiation probe backed by JAX."""

    name: ClassVar[str] = "jax"
    capabilities: ClassVar[list[str]] = [
        "automatic_differentiation", "grad", "jacobian", "hessian",
    ]

    # ------------------------------------------------------------------ #
    #  Availability
    # ------------------------------------------------------------------ #
    @classmethod
    def _probe_version(cls) -> str:
        import importlib

        jax = importlib.import_module("jax")
        return str(getattr(jax, "__version__", "unknown"))

    # ------------------------------------------------------------------ #
    #  Input validation
    # ------------------------------------------------------------------ #
    def validate_input(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("jax: payload must be an object")
        operation = str(payload.get("operation", "grad"))
        if operation not in ("grad", "jacobian", "hessian"):
            raise ValueError(
                f"jax: operation must be 'grad', 'jacobian', or 'hessian'; got {operation!r}"
            )
        if "x" not in payload:
            raise ValueError("jax: payload needs 'x' for differentiation")
        x_raw = payload["x"]
        if isinstance(x_raw, bool):
            raise ValueError("jax: x must not be boolean")
        if isinstance(x_raw, (int, float)):
            pass
        elif isinstance(x_raw, (list, tuple)):
            if len(x_raw) == 0:
                raise ValueError("jax: x must not be empty")
            for v in x_raw:
                _ = float(v)
        else:
            raise ValueError("jax: x must be a number or list of numbers")

    # ------------------------------------------------------------------ #
    #  Execution
    # ------------------------------------------------------------------ #
    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        operation = str(payload.get("operation", "grad"))
        x_raw = payload["x"]
        function_expr = str(payload.get("function", "x**2"))
        # The expression is validated and translated BEFORE the availability
        # gate and before JAX is imported, so hostile text is rejected as a
        # ValueError and can never reach an evaluating sympy parser.
        symbols, expr = _parsed_function(function_expr)
        meta = self.availability()
        if not meta.available:
            reason = meta.reason or "No module named 'jax'"
            raise RuntimeError(
                f"TOOL_UNAVAILABLE: jax is not installed ({reason})"
            )

        import jax
        import jax.numpy as jnp  # noqa: F401 -- imported for availability
        import sympy

        x = jnp.asarray(x_raw, dtype=float)
        raw_fn = sympy.lambdify(symbols["x"], expr, modules="jax")

        def f(z: Any) -> Any:
            return jnp.sum(raw_fn(z))

        backend = f"jax-{jax.__version__}"
        x_out = float(x_raw) if isinstance(x_raw, (int, float)) else x_raw

        if operation == "grad":
            result = jax.grad(f)(x)
            value = _to_native(result)
            return {"status": "PASS", "operation": "grad", "backend": backend,
                    "x": x_out, "function": function_expr, "gradient": value}

        if operation == "jacobian":
            result = jax.jacfwd(f)(x)
            value = _to_native(result)
            return {"status": "PASS", "operation": "jacobian", "backend": backend,
                    "x": x_out, "function": function_expr, "jacobian": value}

        # hessian
        result = jax.hessian(f)(x)
        value = _to_native(result)
        return {"status": "PASS", "operation": "hessian", "backend": backend,
                "x": x_out, "function": function_expr, "hessian": value}


def _to_native(value: Any) -> Any:
    """Convert a JAX tracer/array into a JSON-serialisable Python value."""
    import numpy as np

    arr = np.asarray(value, dtype=float)
    if arr.ndim == 0:
        return float(arr)
    return arr.tolist()
