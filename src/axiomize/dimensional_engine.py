"""Equation-level dimensional consistency checks for versioned Model IR."""

from __future__ import annotations

import ast
from typing import Any

from axiomize.validation.dimensions import dimension_of

_ALLOWED_FUNCTIONS = {
    "sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh",
    "exp", "log", "sqrt", "Abs", "Min", "Max", "Heaviside",
}


def _combine(left: dict[str, float], right: dict[str, float], sign: float = 1.0) -> dict[str, float]:
    out = dict(left)
    for key, value in right.items():
        out[key] = out.get(key, 0.0) + sign * float(value)
        if abs(out[key]) < 1e-12:
            out.pop(key, None)
    return out


def _same(left: dict[str, float], right: dict[str, float], tol: float = 1e-12) -> bool:
    return all(abs(left.get(k, 0.0) - right.get(k, 0.0)) <= tol for k in set(left) | set(right))


def _parse_dimension(expression: str, dimensions: dict[str, dict[str, float]]) -> dict[str, float]:
    tree = ast.parse(expression, mode="eval")

    def visit(node: ast.AST) -> dict[str, float]:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise ValueError("only numeric constants are allowed")
            return {}
        if isinstance(node, ast.Name):
            if node.id not in dimensions:
                raise ValueError(f"unknown symbol {node.id!r}")
            return dict(dimensions[node.id])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return visit(node.operand)
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub, ast.Mod)):
                if not _same(left, right):
                    raise ValueError(f"additive dimension mismatch: {left} vs {right}")
                return left
            if isinstance(node.op, ast.Mult):
                return _combine(left, right)
            if isinstance(node.op, ast.Div):
                return _combine(left, right, -1.0)
            if isinstance(node.op, ast.Pow):
                if right:
                    raise ValueError("dimensional exponent is invalid")
                if not isinstance(node.right, ast.Constant) or not isinstance(node.right.value, (int, float)):
                    raise ValueError("exponent must be a numeric constant for dimensional analysis")
                exponent = float(node.right.value)
                return {k: v * exponent for k, v in left.items() if abs(v * exponent) > 1e-12}
            raise ValueError(f"unsupported operator {type(node.op).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCTIONS:
                raise ValueError("unsupported function in dimensional expression")
            name = node.func.id
            args = [visit(arg) for arg in node.args]
            if name == "Abs":
                if len(args) != 1:
                    raise ValueError("Abs expects one argument")
                return args[0]
            if name in {"Min", "Max"}:
                if not args or any(not _same(args[0], other) for other in args[1:]):
                    raise ValueError(f"{name} arguments must have equal dimensions")
                return args[0]
            if name == "sqrt":
                if len(args) != 1:
                    raise ValueError("sqrt expects one argument")
                return {k: v / 2.0 for k, v in args[0].items()}
            if any(args):
                raise ValueError(f"{name} requires dimensionless arguments")
            return {}
        raise ValueError(f"unsupported syntax {type(node).__name__}")

    return visit(tree)


def equation_dimension_checks(model: Any) -> list[dict[str, Any]]:
    """Return explicit PASS/FAIL checks for each equation in a Model IR."""
    dimensions: dict[str, dict[str, float]] = {}
    units: dict[str, str] = {}
    for variable in model.variables:
        dimensions[variable.name] = {k: float(v) for k, v in dimension_of(variable.unit).exponents.items()}
        units[variable.name] = variable.unit
    for parameter in model.parameters:
        dimensions[parameter.name] = {k: float(v) for k, v in dimension_of(parameter.unit).exponents.items()}
        units[parameter.name] = parameter.unit
    independent = {k: float(v) for k, v in dimension_of(model.independent_unit).exponents.items()}
    dimensions[model.independent_variable] = independent
    units[model.independent_variable] = model.independent_unit

    checks: list[dict[str, Any]] = []
    for index, equation in enumerate(model.equations):
        check_name = f"equation_dimension:{equation.target or index}"
        try:
            actual = _parse_dimension(equation.expression, dimensions)
            expected = None
            basis = ""
            if equation.unit:
                expected = {k: float(v) for k, v in dimension_of(equation.unit).exponents.items()}
                basis = f"declared unit {equation.unit}"
            elif equation.kind == "derivative":
                if equation.target not in dimensions:
                    raise ValueError(f"unknown derivative target {equation.target!r}")
                expected = _combine(dimensions[equation.target], independent, -1.0)
                basis = f"d({equation.target})/d({model.independent_variable})"
            elif equation.target:
                if equation.target not in dimensions:
                    raise ValueError(f"unknown target {equation.target!r}")
                expected = dimensions[equation.target]
                basis = f"target {equation.target} [{units[equation.target]}]"

            if expected is None:
                status = "UNVERIFIED"
                detail = f"expression_dimension={actual}; residual has no declared unit"
            else:
                status = "PASS" if _same(actual, expected) else "FAIL"
                detail = f"actual={actual}; expected={expected}; basis={basis}"
            checks.append({"name": check_name, "status": status, "detail": detail})
        except Exception as exc:
            checks.append({"name": check_name, "status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"})
    return checks


def merge_dimension_checks(validation: dict[str, Any], model: Any) -> dict[str, Any]:
    """Merge equation checks into validation without hiding prior results."""
    out = dict(validation)
    checks = list(out.get("checks", []))
    equation_checks = equation_dimension_checks(model)
    checks.extend(equation_checks)
    out["checks"] = checks
    if any(item.get("status") == "FAIL" for item in equation_checks):
        out["status"] = "FAIL"
    out["equation_dimension_checks"] = equation_checks
    return out
