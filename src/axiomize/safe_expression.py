"""Hardened parser for user-supplied mathematical expressions.

Axiomize accepts equations from Model IR and symbolic-tool calls.  This module is
the single parser policy for those strings: only a small arithmetic AST is
accepted, symbols/functions are explicit, and complexity is bounded before
SymPy sees the expression.  This prevents Python-evaluation constructs and
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

# Builtins / implementation-ish names are deliberately excluded from model
# namespaces even if they would only be treated as SymPy Symbols.
RESERVED_SYMBOLS = ALLOWED_FUNCTIONS | frozenset({
    "True", "False", "None", "nan", "inf", "oo", "I", "E", "pi",
})

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
    ast.Tuple,  # required by Piecewise pair syntax: Piecewise((x, cond), ...)
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
    if text.startswith("_") or "__" in text:
        raise ValueError(f"{what} {text!r} uses a reserved implementation-style name")
    if text in RESERVED_SYMBOLS:
        raise ValueError(f"{what} {text!r} collides with a reserved mathematical name")
    return text


def _depth(node: ast.AST) -> int:
    children = list(ast.iter_child_nodes(node))
    return 1 if not children else 1 + max(_depth(child) for child in children)


def _check_constant(value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("only real numeric constants are allowed")
    if isinstance(value, int) and len(str(abs(value))) > MAX_INTEGER_DIGITS:
        raise ValueError(f"integer literal exceeds {MAX_INTEGER_DIGITS} digits")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("numeric constants must be finite")


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
        elif isinstance(node, ast.Pow) and isinstance(node.right, ast.Constant):
            _check_constant(node.right.value)
            exponent = float(node.right.value)
            if abs(exponent) > MAX_ABS_CONSTANT_EXPONENT:
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
        if hasattr(sp, name):
            local_dict[name] = getattr(sp, name)
    # ``sympify`` is only reached after the Python AST and namespace have been
    # whitelisted above.  No Python attribute/subscript/lambda/import syntax can
    # survive that gate.
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
    return {name: sp.Symbol(name, real=True) for name in sorted(bare)}
