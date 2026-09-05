"""Z3 logical-constraint verification adapter (PHASE 5).

Checks whether a set of inequality/equality constraints over bounded real
variables is jointly satisfiable. Constraint strings are parsed through a small
AST translator; Python ``eval`` is never used.
"""

from __future__ import annotations

import ast
import math
from typing import Any, ClassVar

from axiomize.limits import MAX_EXPRESSION_CHARS, MAX_EXPRESSION_NODES
from axiomize.safe_expression import validate_identifier
from axiomize.tools.base import ScientificTool
from axiomize.validation.status import ValidationStatus

_MAX_CONSTRAINTS = 10_000
_MAX_VARIABLES = 2_048


class Z3Tool(ScientificTool):
    name: ClassVar[str] = "z3"
    capabilities: ClassVar[list[str]] = ["sat_check", "constraint_verification", "model_sampling"]

    @classmethod
    def _probe_version(cls) -> str:
        import z3  # type: ignore[import-untyped]

        return str(z3.get_version_string())

    def validate_input(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("z3: payload must be an object")
        if "constraints" not in payload or "variables" not in payload:
            raise ValueError("z3: payload needs 'constraints' and 'variables'")
        if not isinstance(payload["constraints"], list):
            raise ValueError("z3: constraints must be an array")
        if not isinstance(payload["variables"], dict):
            raise ValueError("z3: variables must be an object")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_input(payload)
        result = check_constraints(payload["constraints"], payload["variables"])
        return {"sat": result["sat"], "model": result["model"], "status": result["status"].value}


def _finite_number(value: Any, *, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _parse_constraint(text: str, symbols: dict[str, Any]) -> Any:
    """Translate a restricted Python-like arithmetic/logic expression to Z3."""
    import z3  # type: ignore[import-untyped]

    if not isinstance(text, str) or not text.strip():
        raise ValueError("constraint must be a non-empty string")
    if len(text) > MAX_EXPRESSION_CHARS:
        raise ValueError(f"constraint exceeds hard limit of {MAX_EXPRESSION_CHARS} characters")
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError, MemoryError) as exc:
        raise ValueError(f"invalid Z3 constraint syntax: {exc}") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_EXPRESSION_NODES:
        raise ValueError(f"constraint exceeds hard AST-node limit of {MAX_EXPRESSION_NODES}")

    def visit(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return z3.BoolVal(node.value)
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                value = _finite_number(node.value, name="constraint constant")
                return z3.RealVal(repr(value))
            raise ValueError("constraints allow only real numeric or boolean constants")
        if isinstance(node, ast.Name):
            if node.id not in symbols:
                raise ValueError(f"unknown variable in constraint: {node.id}")
            return symbols[node.id]
        if isinstance(node, ast.UnaryOp):
            operand = visit(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return operand
            if isinstance(node.op, ast.Not):
                return z3.Not(operand)
            raise ValueError(f"unsupported unary operator: {type(node.op).__name__}")
        if isinstance(node, ast.BinOp):
            left = visit(node.left)
            right = visit(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                # Keep real-arithmetic constraints in a decidable/practical
                # subset: only literal non-negative integer powers are allowed.
                exponent_node = node.right
                sign = 1
                if isinstance(exponent_node, ast.UnaryOp) and isinstance(exponent_node.op, ast.USub):
                    sign = -1
                    exponent_node = exponent_node.operand
                if (
                    sign < 0
                    or not isinstance(exponent_node, ast.Constant)
                    or isinstance(exponent_node.value, bool)
                    or not isinstance(exponent_node.value, int)
                    or exponent_node.value > 32
                ):
                    raise ValueError("constraint powers require an integer literal exponent in [0, 32]")
                return left ** int(exponent_node.value)
            raise ValueError(f"unsupported binary operator: {type(node.op).__name__}")
        if isinstance(node, ast.Compare):
            if len(node.ops) != len(node.comparators):
                raise ValueError("malformed comparison")
            current = visit(node.left)
            clauses: list[Any] = []
            for op, comparator in zip(node.ops, node.comparators):
                right = visit(comparator)
                if isinstance(op, ast.Lt):
                    clauses.append(current < right)
                elif isinstance(op, ast.LtE):
                    clauses.append(current <= right)
                elif isinstance(op, ast.Gt):
                    clauses.append(current > right)
                elif isinstance(op, ast.GtE):
                    clauses.append(current >= right)
                elif isinstance(op, ast.Eq):
                    clauses.append(current == right)
                elif isinstance(op, ast.NotEq):
                    clauses.append(current != right)
                else:
                    raise ValueError(f"unsupported comparison operator: {type(op).__name__}")
                current = right
            return clauses[0] if len(clauses) == 1 else z3.And(*clauses)
        if isinstance(node, ast.BoolOp):
            values = [visit(value) for value in node.values]
            if isinstance(node.op, ast.And):
                return z3.And(*values)
            if isinstance(node.op, ast.Or):
                return z3.Or(*values)
            raise ValueError(f"unsupported boolean operator: {type(node.op).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in {"And", "Or", "Not"}:
                raise ValueError("only And(...), Or(...), and Not(...) calls are allowed")
            if node.keywords:
                raise ValueError("keyword arguments are not allowed in constraints")
            args = [visit(arg) for arg in node.args]
            if node.func.id == "Not":
                if len(args) != 1:
                    raise ValueError("Not(...) requires exactly one argument")
                return z3.Not(args[0])
            if not args:
                raise ValueError(f"{node.func.id}(...) requires at least one argument")
            return z3.And(*args) if node.func.id == "And" else z3.Or(*args)
        raise ValueError(f"unsupported constraint syntax: {type(node).__name__}")

    translated = visit(tree)
    if not z3.is_bool(translated):
        raise ValueError("constraint expression must evaluate to a Boolean relation")
    return translated


def _z3_number_to_float(value: Any) -> float:
    import z3  # type: ignore[import-untyped]

    if z3.is_rational_value(value):
        return value.numerator_as_long() / value.denominator_as_long()
    decimal = str(value.as_decimal(16)).rstrip("?")
    if decimal.endswith("/"):
        raise ValueError(f"cannot convert Z3 model value {value!s} to float")
    return float(decimal)


def check_constraints(
    constraints: list[str],
    variables: dict[str, tuple[float, float]],
) -> dict[str, Any]:
    """Check satisfiability of bounded real-arithmetic constraints safely."""
    import z3  # type: ignore[import-untyped]

    if not isinstance(constraints, list):
        raise ValueError("constraints must be an array")
    if len(constraints) > _MAX_CONSTRAINTS:
        raise ValueError(f"constraints exceed hard limit of {_MAX_CONSTRAINTS}")
    if not isinstance(variables, dict):
        raise ValueError("variables must be an object")
    if not variables or len(variables) > _MAX_VARIABLES:
        raise ValueError(f"variables must contain 1..{_MAX_VARIABLES} entries")

    scope: dict[str, Any] = {}
    normalized_bounds: dict[str, tuple[float, float]] = {}
    for raw_name, raw_bounds in variables.items():
        name = validate_identifier(str(raw_name), what="Z3 variable name")
        if not isinstance(raw_bounds, (list, tuple)) or len(raw_bounds) != 2:
            raise ValueError(f"bounds for {name!r} must contain [low, high]")
        low = _finite_number(raw_bounds[0], name=f"{name} lower bound")
        high = _finite_number(raw_bounds[1], name=f"{name} upper bound")
        if low > high:
            raise ValueError(f"{name} lower bound must be <= upper bound")
        scope[name] = z3.Real(name)
        normalized_bounds[name] = (low, high)

    solver = z3.Solver()
    for name, (low, high) in normalized_bounds.items():
        solver.add(scope[name] >= z3.RealVal(repr(low)), scope[name] <= z3.RealVal(repr(high)))
    for text in constraints:
        solver.add(_parse_constraint(text, scope))

    verdict = solver.check()
    if verdict == z3.sat:
        model = solver.model()
        values: dict[str, float] = {}
        for name in scope:
            value = model.eval(scope[name], model_completion=True)
            values[name] = _z3_number_to_float(value)
        return {"sat": True, "model": values, "status": ValidationStatus.PASS}
    if verdict == z3.unsat:
        return {"sat": False, "model": None, "status": ValidationStatus.FAIL}
    return {"sat": None, "model": None, "status": ValidationStatus.INCONCLUSIVE}
