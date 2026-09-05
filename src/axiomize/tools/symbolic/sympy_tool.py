"""SymPy symbolic-validation adapter (PHASE 1).

All user expressions pass through :mod:`axiomize.safe_expression` before SymPy;
``sympify`` is never called on unchecked Python-like text.
"""

from __future__ import annotations

from typing import Any, ClassVar

from axiomize.safe_expression import auto_symbol_map, sympy_expression, validate_identifier
from axiomize.tools.base import ScientificTool


def _sympy():  # type: ignore[no-any-unimported]
    import sympy  # type: ignore[import-untyped]

    return sympy


def _symbols_for(*expressions: str, extra: tuple[str, ...] = ()) -> dict[str, Any]:
    sp = _sympy()
    names: set[str] = set()
    for expression in expressions:
        names.update(auto_symbol_map(str(expression)))
    for name in extra:
        names.add(validate_identifier(str(name), what="symbol"))
    return {name: sp.Symbol(name, real=True) for name in sorted(names)}


def _sympify(text: str, *, symbols: dict[str, Any] | None = None):
    mapping = symbols if symbols is not None else _symbols_for(text)
    return sympy_expression(str(text), mapping)


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
        if "expression" not in payload:
            raise ValueError("sympy: payload needs an 'expression' string")
        if not isinstance(payload["expression"], str) or not payload["expression"].strip():
            raise ValueError("sympy: expression must be a non-empty string")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        action = payload.get("action", "simplify")
        if action == "simplify":
            return {"result": simplify_expr(str(payload["expression"]))}
        if action == "differentiate":
            return {"result": differentiate(
                str(payload["expression"]), str(payload.get("variable", "x")))}
        if action == "equivalence":
            return {"result": check_equivalence(
                str(payload["expression"]), str(payload.get("other", "")))}
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
    if not isinstance(expressions, list) or not expressions:
        raise ValueError("expressions must be a non-empty array")
    if not isinstance(variables, list) or not variables:
        raise ValueError("variables must be a non-empty array")
    checked_variables = tuple(validate_identifier(v, what="Jacobian variable") for v in variables)
    symbols = _symbols_for(*expressions, extra=checked_variables)
    vec = sp.Matrix([_sympify(e, symbols=symbols) for e in expressions])
    syms = [symbols[v] for v in checked_variables]
    return [[str(entry) for entry in row] for row in vec.jacobian(syms).tolist()]


def check_equivalence(first: str, second: str) -> bool:
    sp = _sympy()
    symbols = _symbols_for(first, second)
    return bool(sp.simplify(
        _sympify(first, symbols=symbols) - _sympify(second, symbols=symbols)
    ) == 0)


def final_size_symbolic(r0: float) -> float:
    """Final epidemic size via SymPy nsolve of z = 1 - exp(-R0 z)."""
    if r0 <= 1:
        return 0.0
    sp = _sympy()
    z = sp.Symbol("z")
    root = sp.nsolve(1 - sp.exp(-r0 * z) - z, 0.5, tol=1e-14, maxsteps=100)
    return float(root)


def find_singularities(expression: str, variable: str) -> list[str]:
    sp = _sympy()
    variable = validate_identifier(variable, what="singularity variable")
    symbols = _symbols_for(expression, extra=(variable,))
    expr = _sympify(expression, symbols=symbols)
    _, denominator = sp.fraction(sp.together(expr))
    if denominator == 1:
        return []
    return [str(s) for s in sp.solve(denominator, symbols[variable])]
