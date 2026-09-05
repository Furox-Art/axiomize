"""SymPy symbolic-validation adapter (PHASE 1).

All user expressions pass through :mod:`axiomize.safe_expression` and are
translated from a bounded AST directly to SymPy. Symbolic matrix dimensions are
also hard-bounded before allocation.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar

from axiomize.limits import MAX_MODEL_EQUATIONS, MAX_MODEL_VARIABLES, enforce_result_cells
from axiomize.safe_expression import auto_symbol_map, sympy_expression, validate_identifier
from axiomize.tools.base import ScientificTool


def _sympy():
    import sympy  # type: ignore[import-untyped]
    return sympy


def _symbols_for(*expressions: str, extra: tuple[str, ...] = ()) -> dict[str, Any]:
    sp = _sympy()
    names: set[str] = set()
    for expression in expressions:
        names.update(auto_symbol_map(str(expression)))
    for name in extra:
        names.add(validate_identifier(str(name), what="symbol"))
    if len(names) > MAX_MODEL_VARIABLES + MAX_MODEL_PARAMETERS:
        raise ValueError("symbolic expression namespace exceeds hard symbol limit")
    return {name: sp.Symbol(name, real=True) for name in sorted(names)}


def _sympify(text: str, *, symbols: dict[str, Any] | None = None):
    mapping = symbols if symbols is not None else _symbols_for(text)
    return sympy_expression(str(text), mapping)


# Imported separately to keep the expression above readable and avoid a magic
# duplicated parameter count.
from axiomize.limits import MAX_MODEL_PARAMETERS  # noqa: E402


class SymPyTool(ScientificTool):
    name: ClassVar[str] = "sympy"
    capabilities: ClassVar[list[str]] = [
        "simplify", "differentiate", "jacobian", "equivalence",
        "analytic_final_size", "singularities",
    ]

    @classmethod
    def _probe_version(cls) -> str:
        return str(_sympy().__version__)

    def validate_input(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict) or "expression" not in payload:
            raise ValueError("sympy: payload needs an 'expression' string")
        if not isinstance(payload["expression"], str) or not payload["expression"].strip():
            raise ValueError("sympy: expression must be a non-empty string")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        action = payload.get("action", "simplify")
        if action == "simplify":
            return {"result": simplify_expr(str(payload["expression"]))}
        if action == "differentiate":
            return {"result": differentiate(str(payload["expression"]), str(payload.get("variable", "x")))}
        if action == "equivalence":
            other = payload.get("other")
            if not isinstance(other, str) or not other.strip():
                raise ValueError("sympy: equivalence needs a non-empty 'other' expression")
            return {"result": check_equivalence(str(payload["expression"]), other)}
        raise ValueError(f"sympy: unknown action {action!r}")

    def metadata(self):  # type: ignore[override]
        return super().metadata()


def simplify_expr(expression: str) -> str:
    sp = _sympy()
    return str(sp.simplify(_sympify(expression)))


def differentiate(expression: str, variable: str) -> str:
    sp = _sympy()
    variable = validate_identifier(variable, what="differentiation variable")
    symbols = _symbols_for(expression, extra=(variable,))
    return str(sp.diff(_sympify(expression, symbols=symbols), symbols[variable]))


def jacobian_matrix(expressions: list[str], variables: list[str]) -> list[list[str]]:
    sp = _sympy()
    if not isinstance(expressions, list) or not expressions or len(expressions) > MAX_MODEL_EQUATIONS:
        raise ValueError(f"expressions must contain 1..{MAX_MODEL_EQUATIONS} strings")
    if not all(isinstance(value, str) and value.strip() for value in expressions):
        raise ValueError("every Jacobian expression must be a non-empty string")
    if not isinstance(variables, list) or not variables or len(variables) > MAX_MODEL_VARIABLES:
        raise ValueError(f"variables must contain 1..{MAX_MODEL_VARIABLES} names")
    enforce_result_cells(len(expressions), len(variables), name="symbolic Jacobian")
    checked_variables = tuple(validate_identifier(v, what="Jacobian variable") for v in variables)
    if len(set(checked_variables)) != len(checked_variables):
        raise ValueError("Jacobian variables must be unique")
    symbols = _symbols_for(*expressions, extra=checked_variables)
    vec = sp.Matrix([_sympify(e, symbols=symbols) for e in expressions])
    syms = [symbols[v] for v in checked_variables]
    return [[str(entry) for entry in row] for row in vec.jacobian(syms).tolist()]


def check_equivalence(first: str, second: str) -> bool:
    sp = _sympy()
    symbols = _symbols_for(first, second)
    return bool(sp.simplify(_sympify(first, symbols=symbols) - _sympify(second, symbols=symbols)) == 0)


def final_size_symbolic(r0: float) -> float:
    """Final epidemic size via SymPy nsolve of z = 1 - exp(-R0 z)."""
    try:
        r0 = float(r0)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("r0 must be numeric") from exc
    if not math.isfinite(r0) or r0 < 0:
        raise ValueError("r0 must be finite and non-negative")
    if r0 <= 1:
        return 0.0
    sp = _sympy()
    z = sp.Symbol("z")
    root = sp.nsolve(1 - sp.exp(-r0 * z) - z, 0.5, tol=1e-14, maxsteps=100)
    value = float(root)
    if not math.isfinite(value) or value < 0 or value > 1:
        raise RuntimeError("symbolic final-size root is outside [0, 1]")
    return value


def find_singularities(expression: str, variable: str) -> list[str]:
    sp = _sympy()
    variable = validate_identifier(variable, what="singularity variable")
    symbols = _symbols_for(expression, extra=(variable,))
    expr = _sympify(expression, symbols=symbols)
    _, denominator = sp.fraction(sp.together(expr))
    if denominator == 1:
        return []
    roots = sp.solve(denominator, symbols[variable])
    if len(roots) > MAX_MODEL_EQUATIONS:
        raise ValueError("symbolic singularity result exceeds hard result count")
    return [str(value) for value in roots]
