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
    MAX_BINOMIAL_ARGUMENT,
    MAX_EXPRESSION_CHARS,
    MAX_EXPRESSION_DEPTH,
    MAX_EXPRESSION_NODES,
    MAX_FACTORIAL_ARGUMENT,
    MAX_INTEGER_DIGITS,
    MAX_INTEGER_FOLD_BITS,
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


# Functions whose SymPy evaluation expands into a large integer. They are only
# ever folded for *constant* arguments that are inside the allow-listed ranges
# above; a symbolic or oversized argument is rejected rather than evaluated.
#
# NOTE: these names are deliberately absent from ALLOWED_FUNCTIONS. `product`
# in particular has no two-argument form in SymPy (``sp.product(2, 3)`` raises
# ``ValueError: Invalid limits given``), so exposing it as a plain function would
# turn a bounded integer expression into a guaranteed runtime error. The folder
# understands the call shapes anyway so the guard stays correct if the allow-list
# ever grows.
_INTEGER_EXPANSIVE_FUNCTIONS = frozenset({"factorial", "product", "binomial"})


def _fold_bounded(value: int, *, what: str) -> int:
    """Return ``value`` only if it fits inside the folded-integer ceiling."""
    if value.bit_length() > MAX_INTEGER_FOLD_BITS:
        raise ValueError(
            f"{what} exceeds the hard folded-constant limit of {MAX_INTEGER_FOLD_BITS} bits"
        )
    return value


def _fold_integer_constant(node: ast.AST) -> int | None:
    """Fold a pure-integer constant subtree to a Python ``int``.

    Returns ``None`` when the subtree is not an integer constant (it contains a
    symbol, a call, a comparison, ...), which means "leave it symbolic".

    This is what makes the exponent ceiling enforceable. ``_constant_number``
    only recognises a literal, so ``9**(10**9)`` used to reach SymPy with a
    billion-digit exponent and never return. Folding rejects that payload before
    any bigint is allocated: every intermediate result is bounded by
    ``MAX_INTEGER_FOLD_BITS`` and the exponent is range-checked before the power
    is computed.
    """
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int):
            return None
        _check_constant(node.value)
        return _fold_bounded(node.value, what="integer literal")

    if isinstance(node, ast.UnaryOp):
        inner = _fold_integer_constant(node.operand)
        if inner is None:
            return None
        if isinstance(node.op, ast.USub):
            return _fold_bounded(-inner, what="negated integer constant")
        if isinstance(node.op, ast.UAdd):
            return inner
        return None

    if isinstance(node, ast.BinOp):
        left = _fold_integer_constant(node.left)
        right = _fold_integer_constant(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return _fold_bounded(left + right, what="integer sum")
        if isinstance(node.op, ast.Sub):
            return _fold_bounded(left - right, what="integer difference")
        if isinstance(node.op, ast.Mult):
            return _fold_bounded(left * right, what="integer product")
        if isinstance(node.op, ast.FloorDiv):
            if right == 0:
                raise ValueError("integer division by zero")
            return _fold_bounded(left // right, what="integer quotient")
        if isinstance(node.op, ast.Mod):
            if right == 0:
                raise ValueError("integer modulo by zero")
            return _fold_bounded(left % right, what="integer remainder")
        if isinstance(node.op, ast.Pow):
            # Range-check the exponent *before* powering: this ordering is the
            # whole point of the guard.
            if abs(right) > MAX_ABS_CONSTANT_EXPONENT:
                raise ValueError(
                    "constant exponent magnitude exceeds hard limit "
                    f"{MAX_ABS_CONSTANT_EXPONENT:g}"
                )
            if right < 0:
                # Negative constant exponents produce reciprocals; keep them
                # symbolic rather than folding into a Fraction.
                return None
            base = abs(left)
            if base > 1 and base.bit_length() * right > MAX_INTEGER_FOLD_BITS:
                raise ValueError(
                    f"constant power exceeds the hard folded-constant limit of "
                    f"{MAX_INTEGER_FOLD_BITS} bits"
                )
            return _fold_bounded(left ** right, what="integer power")
        return None

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id
        if name not in _INTEGER_EXPANSIVE_FUNCTIONS or node.keywords:
            return None
        args = [_fold_integer_constant(arg) for arg in node.args]
        if any(value is None for value in args):
            return None
        integers = [int(value) for value in args]
        if name == "factorial":
            if len(integers) != 1:
                raise ValueError("factorial takes exactly one integer argument")
            if not 0 <= integers[0] <= MAX_FACTORIAL_ARGUMENT:
                raise ValueError(
                    f"factorial argument must be an integer in [0, {MAX_FACTORIAL_ARGUMENT}]"
                )
            return _fold_bounded(math.factorial(integers[0]), what="factorial")
        if name == "binomial":
            if len(integers) != 2:
                raise ValueError("binomial takes exactly two integer arguments")
            if any(value < 0 or value > MAX_BINOMIAL_ARGUMENT for value in integers):
                raise ValueError(
                    "binomial arguments must be integers in "
                    f"[0, {MAX_BINOMIAL_ARGUMENT}]"
                )
            return _fold_bounded(math.comb(*integers), what="binomial")
        if name == "product":
            if len(integers) != 2:
                raise ValueError("product takes exactly two integer arguments")
            low, high = min(integers), max(integers)
            if low < 0 or high - low > MAX_FACTORIAL_ARGUMENT:
                raise ValueError(
                    "product range must satisfy 0 <= start <= end <= start + "
                    f"{MAX_FACTORIAL_ARGUMENT}"
                )
            result = 1
            for value in range(low, high + 1):
                result *= value
            return _fold_bounded(result, what="product")
        return None

    return None


def _needs_expansion_check(node: ast.AST) -> bool:
    """True for nodes that can expand into a large constant integer."""
    if isinstance(node, ast.BinOp):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _INTEGER_EXPANSIVE_FUNCTIONS
    )


def _enforce_constant_expansion_bounds(tree: ast.Expression) -> None:
    """Reject constant-only subtrees whose expansion exceeds hard ceilings.

    Applies the folded-integer ceiling to every binary operator and to every
    integer-expansive call, so neither nested powers nor oversized combinatorial
    arguments can build an unbounded intermediate before SymPy sees them.
    """
    for node in ast.walk(tree):
        if _needs_expansion_check(node):
            _fold_integer_constant(node)


def _exponent_magnitude(node: ast.AST) -> float | None:
    """Best-effort magnitude of a power exponent, folding integer subtrees."""
    exponent = _constant_number(node)
    if exponent is not None:
        return exponent
    folded = _fold_integer_constant(node)
    if folded is None:
        return None
    return float(folded)


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
            # Fold nested exponent subtrees (``10**9``) as well as plain literals
            # so a nested power cannot smuggle a huge exponent past the ceiling.
            exponent = _exponent_magnitude(node.right)
            if exponent is not None and abs(exponent) > MAX_ABS_CONSTANT_EXPONENT:
                raise ValueError(
                    f"constant exponent magnitude exceeds hard limit {MAX_ABS_CONSTANT_EXPONENT:g}"
                )
        elif isinstance(node, ast.Compare):
            if len(node.ops) != 1 or len(node.comparators) != 1:
                raise ValueError("chained comparisons are not allowed")

    # Bound constant-only expansion across the whole tree (nested powers,
    # factorial/binomial/product arguments, oversized intermediate products).
    _enforce_constant_expansion_bounds(tree)

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
