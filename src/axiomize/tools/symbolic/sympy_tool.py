"""SymPy symbolic-validation adapter (PHASE 1)."""

from __future__ import annotations

from typing import Any, ClassVar

from axiomize.tools.base import ScientificTool


def _sympy():  # type: ignore[no-any-unimported]
    import sympy  # type: ignore[import-untyped]

    return sympy


def _sympify(text: str):
    """Parse an expression, forcing bare parameter names to Symbols.

    ``beta`` and ``gamma`` collide with ``sympy.beta`` / ``sympy.gamma``
    (special functions). A name that is a SymPy FunctionClass but is NOT
    called like a function in the text is treated as a plain symbol, so
    SIR-style equations parse as the modeler means them.
    """
    import re

    sp = _sympy()
    local = {}
    for name in set(re.findall(r"[A-Za-z_]\w*", text)):
        obj = getattr(sp, name, None)
        if isinstance(obj, sp.FunctionClass) and not re.search(
            rf"\b{name}\s*\(", text
        ):
            local[name] = sp.Symbol(name)
    return sp.sympify(text, locals=local)


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
    symbol = sp.Symbol(variable)
    return str(sp.diff(_sympify(expression), symbol))


def jacobian_matrix(expressions: list[str], variables: list[str]) -> list[list[str]]:
    sp = _sympy()
    vec = sp.Matrix([_sympify(e) for e in expressions])
    syms = [sp.Symbol(v) for v in variables]
    return [[str(entry) for entry in row] for row in vec.jacobian(syms).tolist()]


def check_equivalence(first: str, second: str) -> bool:
    sp = _sympy()
    return bool(sp.simplify(_sympify(first) - _sympify(second)) == 0)


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
    symbol = sp.Symbol(variable)
    expr = _sympify(expression)
    _, denominator = sp.fraction(sp.together(expr))
    if denominator == 1:
        return []
    return [str(s) for s in sp.solve(denominator, symbol)]
