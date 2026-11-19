"""Equation-level dimensional consistency checks for versioned Model IR."""

from __future__ import annotations

import ast
import math
from typing import Any

from axiomize.safe_expression import validate_expression
from axiomize.validation.dimensions import dimension_of, scale_of

_ALLOWED_FUNCTIONS = {
    "sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh",
    "exp", "log", "sqrt", "Abs", "Min", "Max", "Heaviside",
}


class ModelDimensionMismatch(ValueError):
    """A Model IR failed the mandatory unit/dimensional gate before execution.

    Simulation is fail-closed: a model whose declared units, or whose
    declared-vs-actual equation dimensions, do not agree is never executed.
    The full validation payload is attached so a caller can render the exact
    failing checks instead of guessing from the message.
    """

    def __init__(self, message: str, *, validation: dict[str, Any]) -> None:
        self.validation = validation
        self.failed_checks = [
            check for check in validation.get("checks", []) if check.get("status") == "FAIL"
        ]
        super().__init__(message)


def _combine(left: dict[str, float], right: dict[str, float], sign: float = 1.0) -> dict[str, float]:
    out = dict(left)
    for key, value in right.items():
        out[key] = out.get(key, 0.0) + sign * float(value)
        if abs(out[key]) < 1e-12:
            out.pop(key, None)
    return out


def _same(left: dict[str, float], right: dict[str, float], tol: float = 1e-12) -> bool:
    return all(abs(left.get(k, 0.0) - right.get(k, 0.0)) <= tol for k in set(left) | set(right))


def _parse_dimension_and_scale(
    expression: str,
    dimensions: dict[str, dict[str, float]],
    scales: dict[str, float] | None,
) -> tuple[dict[str, float], float]:
    # Apply the same namespace and complexity guard as executable expressions
    # before running the dedicated dimensional AST evaluator. When ``scales``
    # is None the scale channel is inert (every leaf is 1.0) and only the
    # dimension vector is meaningful; this preserves the dimension-only
    # contract of ``_parse_dimension``.
    tree = validate_expression(
        expression,
        allowed_names=set(dimensions),
        allowed_functions=_ALLOWED_FUNCTIONS,
    )

    def visit(node: ast.AST) -> tuple[dict[str, float], float]:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
                raise ValueError("only numeric constants are allowed")
            return {}, 1.0
        if isinstance(node, ast.Name):
            if node.id not in dimensions:
                raise ValueError(f"unknown symbol {node.id!r}")
            return dict(dimensions[node.id]), (scales[node.id] if scales is not None else 1.0)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return visit(node.operand)
        if isinstance(node, ast.BinOp):
            (left, ls), (right, rs) = visit(node.left), visit(node.right)
            if isinstance(node.op, (ast.Add, ast.Sub, ast.Mod)):
                if not _same(left, right):
                    raise ValueError(f"additive dimension mismatch: {left} vs {right}")
                if scales is not None and not math.isclose(ls, rs, rel_tol=1e-9, abs_tol=1e-12):
                    raise ValueError(f"additive unit-scale mismatch: factor {rs / ls:g}")
                return left, ls
            if isinstance(node.op, ast.Mult):
                return _combine(left, right), ls * rs
            if isinstance(node.op, ast.Div):
                return _combine(left, right, -1.0), ls / rs
            if isinstance(node.op, ast.Pow):
                if right:
                    raise ValueError("dimensional exponent is invalid")
                if not isinstance(node.right, ast.Constant) or not isinstance(node.right.value, (int, float)):
                    raise ValueError("exponent must be a numeric constant for dimensional analysis")
                exponent = float(node.right.value)
                return {k: v * exponent for k, v in left.items() if abs(v * exponent) > 1e-12}, ls ** exponent
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
                if not args or any(not _same(args[0][0], other[0]) for other in args[1:]):
                    raise ValueError(f"{name} arguments must have equal dimensions")
                if scales is not None and any(
                    not math.isclose(args[0][1], other[1], rel_tol=1e-9, abs_tol=1e-12) for other in args[1:]
                ):
                    raise ValueError(f"{name} arguments must have equal unit scales")
                return args[0]
            if name == "sqrt":
                if len(args) != 1:
                    raise ValueError("sqrt expects one argument")
                dim, scale = args[0]
                return {k: v / 2.0 for k, v in dim.items()}, math.sqrt(scale)
            if any(dim for dim, _ in args):
                raise ValueError(f"{name} requires dimensionless arguments")
            return {}, 1.0
        raise ValueError(f"unsupported syntax {type(node).__name__}")

    return visit(tree)


def _parse_dimension(expression: str, dimensions: dict[str, dict[str, float]]) -> dict[str, float]:
    dim, _scale = _parse_dimension_and_scale(expression, dimensions, None)
    return dim


def _parse_scale(expression: str, dimensions: dict[str, dict[str, float]], scales: dict[str, float]) -> float:
    _dim, scale = _parse_dimension_and_scale(expression, dimensions, scales)
    return scale


def _register_advanced_symbols(
    model: Any,
    dimensions: dict[str, dict[str, float]],
    units: dict[str, str],
    scales: dict[str, float] | None = None,
) -> None:
    """Declare deterministic symbols generated by advanced native executors."""
    family = getattr(getattr(model, "family", None), "value", str(getattr(model, "family", "")))
    state_dimensions = {v.name: dict(dimensions[v.name]) for v in model.variables if v.name in dimensions}
    state_units = {v.name: units[v.name] for v in model.variables if v.name in units}
    state_scales = {v.name: scales[v.name] for v in model.variables if scales is not None and v.name in scales}

    if family in {"network", "agent_based"}:
        for name, dim in state_dimensions.items():
            generated = [f"mean_{name}"]
            if family == "network":
                generated.extend([
                    f"neighbor_{name}_sum",
                    f"neighbor_{name}_mean",
                    f"laplacian_{name}",
                ])
            for symbol in generated:
                dimensions[symbol] = dict(dim)
                units[symbol] = state_units[name]
                if scales is not None:
                    scales[symbol] = state_scales[name]
        if family == "network":
            dimensions["degree"] = {}
            units["degree"] = "dimensionless"
            if scales is not None:
                scales["degree"] = 1.0

    metadata = model.metadata if isinstance(getattr(model, "metadata", None), dict) else {}
    declared = metadata.get("symbol_units", {})
    if isinstance(declared, dict):
        for symbol, unit in declared.items():
            dimensions[str(symbol)] = {k: float(v) for k, v in dimension_of(str(unit)).exponents.items()}
            units[str(symbol)] = str(unit)
            if scales is not None:
                scales[str(symbol)] = scale_of(str(unit))

    if family == "bayesian":
        bayesian = metadata.get("bayesian", {})
        if isinstance(bayesian, dict):
            data = bayesian.get("data", {})
            data_units = bayesian.get("data_units", {})
            if isinstance(data, dict):
                for symbol in data:
                    if symbol in dimensions:
                        continue
                    unit = str(data_units.get(symbol, "dimensionless")) if isinstance(data_units, dict) else "dimensionless"
                    dimensions[str(symbol)] = {k: float(v) for k, v in dimension_of(unit).exponents.items()}
                    units[str(symbol)] = unit
                    if scales is not None:
                        scales[str(symbol)] = scale_of(unit)


def _collect_symbol_tables(model: Any) -> tuple[dict[str, dict[str, float]], dict[str, str], dict[str, float]]:
    """Build dimension, unit and canonical-scale tables for every IR symbol."""
    dimensions: dict[str, dict[str, float]] = {}
    units: dict[str, str] = {}
    scales: dict[str, float] = {}
    for variable in model.variables:
        dimensions[variable.name] = {k: float(v) for k, v in dimension_of(variable.unit).exponents.items()}
        units[variable.name] = variable.unit
        scales[variable.name] = scale_of(variable.unit)
    for parameter in model.parameters:
        dimensions[parameter.name] = {k: float(v) for k, v in dimension_of(parameter.unit).exponents.items()}
        units[parameter.name] = parameter.unit
        scales[parameter.name] = scale_of(parameter.unit)
    independent = {k: float(v) for k, v in dimension_of(model.independent_unit).exponents.items()}
    dimensions[model.independent_variable] = independent
    units[model.independent_variable] = model.independent_unit
    scales[model.independent_variable] = scale_of(model.independent_unit)
    _register_advanced_symbols(model, dimensions, units, scales)
    return dimensions, units, scales


def equation_dimension_checks(model: Any) -> list[dict[str, Any]]:
    """Return explicit PASS/FAIL checks for each equation in a Model IR."""
    dimensions, units, _scales = _collect_symbol_tables(model)
    independent = dimensions[model.independent_variable]

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
                detail = f"expression_dimension={actual}; residual/objective has no declared unit"
            else:
                status = "PASS" if _same(actual, expected) else "FAIL"
                detail = f"actual={actual}; expected={expected}; basis={basis}"
            checks.append({"name": check_name, "status": status, "detail": detail})
        except Exception as exc:
            checks.append({"name": check_name, "status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"})
    return checks


def equation_unit_scale_checks(model: Any) -> list[dict[str, Any]]:
    """Fail-closed canonical-scale checks per equation.

    Dimensions agreeing is not enough: a rate in ``1/day`` integrated against
    ``t`` in seconds is off by 86400x. Each equation with a determinable
    expected unit gets an explicit PASS/FAIL scale check carrying the factor,
    so a scale mismatch blocks execution instead of silently passing a wrong
    number. Residual/objective equations without a declared unit are skipped
    (their dimension check is already UNVERIFIED).
    """
    dimensions, _units, scales = _collect_symbol_tables(model)
    checks: list[dict[str, Any]] = []
    for index, equation in enumerate(model.equations):
        check_name = f"equation_unit_scale:{equation.target or index}"
        try:
            actual = _parse_scale(equation.expression, dimensions, scales)
            expected = None
            basis = ""
            if equation.unit:
                expected = scale_of(equation.unit)
                basis = f"declared unit {equation.unit}"
            elif equation.kind == "derivative":
                if equation.target not in scales:
                    raise ValueError(f"unknown derivative target {equation.target!r}")
                expected = scales[equation.target] / scales[model.independent_variable]
                basis = f"d({equation.target})/d({model.independent_variable})"
            elif equation.target:
                if equation.target not in scales:
                    raise ValueError(f"unknown target {equation.target!r}")
                expected = scales[equation.target]
                basis = f"target {equation.target}"
            if expected is None:
                continue
            if math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12):
                checks.append({
                    "name": check_name, "status": "PASS",
                    "detail": f"actual_scale={actual:g}; expected_scale={expected:g}; basis={basis}",
                })
            else:
                checks.append({
                    "name": check_name, "status": "FAIL",
                    "detail": (
                        f"unit-scale mismatch: actual_scale={actual:g}; expected_scale={expected:g}; "
                        f"factor={actual / expected:g}; basis={basis}; convert the values or declare "
                        f"consistent units (e.g. 1/day vs 1/s differs by 86400)"
                    ),
                })
        except Exception as exc:
            checks.append({"name": check_name, "status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"})
    return checks


def merge_dimension_checks(validation: dict[str, Any], model: Any) -> dict[str, Any]:
    """Merge equation checks into validation without hiding prior results.

    An exception raised while deriving dimensions (an unparseable unit, for
    instance) is recorded as a FAIL check rather than propagated. A caller that
    is about to execute the model needs one verdict, not a crash whose severity
    it cannot see; ``status`` is the fail-closed one, so a malformed unit blocks
    the run instead of slipping past it. Canonical-scale checks are merged the
    same way: a scale mismatch is a FAIL, never a silent pass.
    """
    out = dict(validation)
    checks = list(out.get("checks", []))
    try:
        equation_checks = equation_dimension_checks(model)
    except Exception as exc:
        equation_checks = [{
            "name": "equation_dimension_engine",
            "status": "FAIL",
            "detail": f"{type(exc).__name__}: {exc}",
        }]
    try:
        scale_checks = equation_unit_scale_checks(model)
    except Exception as exc:
        scale_checks = [{
            "name": "equation_unit_scale_engine",
            "status": "FAIL",
            "detail": f"{type(exc).__name__}: {exc}",
        }]
    checks.extend(equation_checks)
    checks.extend(scale_checks)
    out["checks"] = checks
    if any(item.get("status") == "FAIL" for item in equation_checks) or any(
        item.get("status") == "FAIL" for item in scale_checks
    ):
        out["status"] = "FAIL"
    out["equation_dimension_checks"] = equation_checks
    out["equation_unit_scale_checks"] = scale_checks
    return out
