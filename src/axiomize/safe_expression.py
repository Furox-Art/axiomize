"""Hardened parser for user-supplied mathematical expressions.

Axiomize accepts equations from Model IR and symbolic-tool calls. This module is
the single parser policy for those strings: only a small arithmetic/relational
AST is accepted, symbols/functions are explicit, complexity is bounded, and the
validated AST is translated directly to SymPy. User text is never passed to
``sympify``/``parse_expr`` for evaluation.
"""

from __future__ import annotations

import ast
import math
import re
from typing import Any

from axiomize.limits import (
    MAX_ABS_CONSTANT_EXPONENT,
    MAX_EXPRESSION_CHARS,
    MAX_EXPRESSION_DEPTH,
    MAX_EXPRESSION_NODES,
    MAX_INTEGER_DIGITS,
)

ALLOWED_FUNCTIONS = frozenset({
    "sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh",
    "exp", "log", "sqrt", "Abs", "Min", "Max", "Piecewise", "Heaviside",
})

RESERVED_SYMBOLS = ALLOWED_FUNCTIONS | frozenset({"True", "False", "None", "nan", "inf", "oo"})
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

_ALLOWED_NODES = (
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.UAdd,
    ast.Call,
    ast.Tuple,
    ast.Compare,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Eq,
    ast.NotEq,
    ast.And,
    ast.Or,
    ast.BoolOp,
)


def validate_identifier(name: str, *, what: str = "symbol") -> str:
    text = str(name)
    if not _IDENTIFIER.fullmatch(text):
        raise ValueError(
            f"{what} {text!r} must start with an ASCII letter and contain only letters, digits, or '_'"
        )
    if "__" in text:
        raise ValueError(f"{what} {text!r} uses a reserved implementation-style name")
    if text in RESERVED_SYMBOLS:
        raise ValueError(f"{what} {text!r} collides with a reserved mathematical name")
    return text


def _depth(node: ast.AST) -> int:
    children = list(ast.iter_child_nodes(node))
    return 1 if not children else 1 + max(_depth(child) for child in children)


def _check_constant(value: Any) -> None:
    if isinstance(value, bool):
        return
    if not isinstance(value, (int, float)):
        raise ValueError("only real numeric or boolean constants are allowed")
    if isinstance(value, int) and len(str(abs(value))) > MAX_INTEGER_DIGITS:
        raise ValueError(f"integer literal exceeds {MAX_INTEGER_DIGITS} digits")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("numeric constants must be finite")


def _constant_number(node: ast.AST) -> float | None:
    sign = 1.0
    current = node
    if isinstance(current, ast.UnaryOp) and isinstance(current.op, (ast.UAdd, ast.USub)):
        sign = -1.0 if isinstance(current.op, ast.USub) else 1.0
        current = current.operand
    if not isinstance(current, ast.Constant) or isinstance(current.value, bool):
        return None
    if not isinstance(current.value, (int, float)):
        return None
    _check_constant(current.value)
    value = sign * float(current.value)
    return value if math.isfinite(value) else None


def validate_expression(
    expression: str,
    *,
    allowed_names: set[str] | frozenset[str],
    allowed_functions: set[str] | frozenset[str] = ALLOWED_FUNCTIONS,
) -> ast.Expression:
    """Validate syntax, namespace and complexity; return the parsed AST."""
    if not isinstance(expression, str):
        raise ValueError("expression must be a string")
    if not expression.strip():
        raise ValueError("expression must be non-empty")
    if len(expression) > MAX_EXPRESSION_CHARS:
        raise ValueError(f"expression exceeds hard limit of {MAX_EXPRESSION_CHARS} characters")

    names = {str(name) for name in allowed_names}
    funcs = {str(name) for name in allowed_functions}
    for name in names:
        validate_identifier(name)
    unknown_funcs = funcs - set(ALLOWED_FUNCTIONS)
    if unknown_funcs:
        raise ValueError(f"unapproved mathematical functions: {sorted(unknown_funcs)}")

    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError, MemoryError) as exc:
        raise ValueError(f"invalid mathematical expression: {exc}") from exc

    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_EXPRESSION_NODES:
        raise ValueError(f"expression exceeds hard AST-node limit of {MAX_EXPRESSION_NODES}")
    if _depth(tree) > MAX_EXPRESSION_DEPTH:
        raise ValueError(f"expression exceeds hard nesting limit of {MAX_EXPRESSION_DEPTH}")

    for node in nodes:
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"unsupported expression syntax: {type(node).__name__}")
        if isinstance(node, ast.Constant):
            _check_constant(node.value)
        elif isinstance(node, ast.Name):
            if node.id not in names and node.id not in funcs:
                raise ValueError(f"unknown symbol in expression: {node.id}")
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in funcs:
                raise ValueError("only approved mathematical functions may be called")
            if node.keywords:
                raise ValueError("keyword arguments are not allowed in mathematical expressions")
            if len(node.args) > 32:
                raise ValueError("mathematical function has too many arguments")
            if node.func.id == "Piecewise":
                if not node.args:
                    raise ValueError("Piecewise requires at least one (expression, condition) pair")
                if any(not isinstance(arg, ast.Tuple) or len(arg.elts) != 2 for arg in node.args):
                    raise ValueError("Piecewise arguments must be (expression, condition) pairs")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            exponent = _constant_number(node.right)
            if exponent is not None and abs(exponent) > MAX_ABS_CONSTANT_EXPONENT:
                raise ValueError(
                    f"constant exponent magnitude exceeds hard limit {MAX_ABS_CONSTANT_EXPONENT:g}"
                )
        elif isinstance(node, ast.Compare):
            if len(node.ops) != 1 or len(node.comparators) != 1:
                raise ValueError("chained comparisons are not allowed")

    return tree


def _to_sympy(node: ast.AST, symbols: dict[str, Any], functions: dict[str, Any]) -> Any:
    import sympy as sp

    if isinstance(node, ast.Expression):
        return _to_sympy(node.body, symbols, functions)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return sp.true if node.value else sp.false
        if isinstance(node.value, int):
            return sp.Integer(node.value)
        if isinstance(node.value, float):
            return sp.Float(node.value)
        raise ValueError("unsupported constant")
    if isinstance(node, ast.Name):
        if node.id in symbols:
            return symbols[node.id]
        raise ValueError(f"unknown symbol in expression: {node.id}")
    if isinstance(node, ast.UnaryOp):
        value = _to_sympy(node.operand, symbols, functions)
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.UAdd):
            return value
        raise ValueError(f"unsupported unary operator: {type(node.op).__name__}")
    if isinstance(node, ast.BinOp):
        left = _to_sympy(node.left, symbols, functions)
        right = _to_sympy(node.right, symbols, functions)
        if isinstance(node.op, ast.Add): return left + right
        if isinstance(node.op, ast.Sub): return left - right
        if isinstance(node.op, ast.Mult): return left * right
        if isinstance(node.op, ast.Div): return left / right
        if isinstance(node.op, ast.Pow): return left ** right
        if isinstance(node.op, ast.Mod): return sp.Mod(left, right)
        raise ValueError(f"unsupported binary operator: {type(node.op).__name__}")
    if isinstance(node, ast.Compare):
        left = _to_sympy(node.left, symbols, functions)
        right = _to_sympy(node.comparators[0], symbols, functions)
        op = node.ops[0]
        if isinstance(op, ast.Lt): return sp.Lt(left, right)
        if isinstance(op, ast.LtE): return sp.Le(left, right)
        if isinstance(op, ast.Gt): return sp.Gt(left, right)
        if isinstance(op, ast.GtE): return sp.Ge(left, right)
        if isinstance(op, ast.Eq): return sp.Eq(left, right)
        if isinstance(op, ast.NotEq): return sp.Ne(left, right)
        raise ValueError(f"unsupported comparison operator: {type(op).__name__}")
    if isinstance(node, ast.BoolOp):
        values = [_to_sympy(value, symbols, functions) for value in node.values]
        if isinstance(node.op, ast.And): return sp.And(*values)
        if isinstance(node.op, ast.Or): return sp.Or(*values)
        raise ValueError(f"unsupported boolean operator: {type(node.op).__name__}")
    if isinstance(node, ast.Tuple):
        return tuple(_to_sympy(value, symbols, functions) for value in node.elts)
    if isinstance(node, ast.Call):
        assert isinstance(node.func, ast.Name)
        function = functions[node.func.id]
        args = [_to_sympy(arg, symbols, functions) for arg in node.args]
        return function(*args)
    raise ValueError(f"unsupported expression syntax: {type(node).__name__}")


def sympy_expression(expression: str, symbols: dict[str, Any]) -> Any:
    """Convert a validated AST directly to a SymPy expression."""
    import sympy as sp

    tree = validate_expression(expression, allowed_names=set(symbols))
    functions = {
        "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
        "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
        "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
        "exp": sp.exp, "log": sp.log, "sqrt": sp.sqrt,
        "Abs": sp.Abs, "Min": sp.Min, "Max": sp.Max,
        "Piecewise": sp.Piecewise, "Heaviside": sp.Heaviside,
    }
    translated = _to_sympy(tree, dict(symbols), functions)
    if isinstance(translated, tuple):
        raise ValueError("top-level mathematical expression cannot be a tuple")
    return translated


def auto_symbol_map(expression: str) -> dict[str, Any]:
    """Build explicit SymPy Symbols for bare names in a standalone expression."""
    import sympy as sp

    if not isinstance(expression, str):
        raise ValueError("expression must be a string")
    if len(expression) > MAX_EXPRESSION_CHARS:
        raise ValueError(f"expression exceeds hard limit of {MAX_EXPRESSION_CHARS} characters")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError, MemoryError) as exc:
        raise ValueError(f"invalid mathematical expression: {exc}") from exc
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    illegal_calls = called - set(ALLOWED_FUNCTIONS)
    if illegal_calls:
        raise ValueError(f"unapproved mathematical functions: {sorted(illegal_calls)}")
    bare = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id not in called and node.id not in ALLOWED_FUNCTIONS
    }
    for name in bare:
        validate_identifier(name)
    symbols = {name: sp.Symbol(name, real=True) for name in sorted(bare)}
    validate_expression(expression, allowed_names=set(symbols))
    return symbols
