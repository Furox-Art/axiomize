"""Hardened parser for user-supplied mathematical expressions.

Axiomize accepts equations from Model IR and symbolic-tool calls. This module is
the single parser policy for those strings: only a small arithmetic AST is
accepted, symbols/functions are explicit, and complexity is bounded before
SymPy sees the expression. This prevents Python-evaluation constructs and
pathological parser inputs from crossing an interface boundary.
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

# Function names must stay distinct because they are injected into SymPy's local
# namespace. Conventional scientific symbols such as I, E, and pi remain legal
# when explicitly declared in Model IR and therefore override SymPy constants.
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
    ast.Tuple,  # Piecewise pair syntax: Piecewise((x, cond), ...)
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
    # Boolean constants are allowed only as declarative mathematical conditions
    # (notably Piecewise(..., True)). They cannot introduce executable behavior.
    if isinstance(value, bool):
        return
    if not isinstance(value, (int, float)):
        raise ValueError("only real numeric or boolean constants are allowed")
    if isinstance(value, int) and len(str(abs(value))) > MAX_INTEGER_DIGITS:
        raise ValueError(f"integer literal exceeds {MAX_INTEGER_DIGITS} digits")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("numeric constants must be finite")


def _constant_number(node: ast.AST) -> float | None:
    """Return a finite literal numeric value, including a unary +/- literal."""
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


def sympy_expression(expression: str, symbols: dict[str, Any]) -> Any:
    """Safely convert a validated arithmetic expression to a SymPy expression."""
    import sympy as sp

    validate_expression(expression, allowed_names=set(symbols))
    local_dict = dict(symbols)
    for name in ALLOWED_FUNCTIONS:
        if name not in local_dict and hasattr(sp, name):
            local_dict[name] = getattr(sp, name)
    # SymPy sees only AST-whitelisted text and an explicit local namespace.
    return sp.sympify(expression, locals=local_dict)


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
