"""Round-2 coverage hardening: Z3 adapter and equation-dimensional engine.

Every test exercises the production code path directly. Optional solver
verdicts (``unknown``) are produced through a deterministic stub installed on
the z3 module boundary; no assertion is postponed or weakened.
"""

from __future__ import annotations

import ast
import math
from types import SimpleNamespace

import pytest
import z3

from axiomize import dimensional_engine as dimension
from axiomize.limits import MAX_Z3_TIMEOUT_MS
from axiomize.model_ir import (
    EquationSpec,
    ModelFamily,
    ModelIR,
    ParameterSpec,
    VariableSpec,
)
from axiomize.tools.logic import z3_tool
from axiomize.validation.status import ValidationStatus

# ---------------------------------------------------------------------------
# Z3 tool: metadata and execute
# ---------------------------------------------------------------------------


def test_z3_tool_availability_reports_real_version() -> None:
    meta = z3_tool.Z3Tool.availability()
    assert meta.available is True
    assert meta.name == "z3"
    assert meta.version
    assert meta.version.lower() != "unknown"


def test_z3_tool_execute_returns_model_and_explicit_timeout() -> None:
    tool = z3_tool.Z3Tool()
    result = tool.execute(
        {
            "constraints": ["x > 1", "x < 2"],
            "variables": {"x": [0.0, 3.0]},
            "timeout_ms": 5000,
        }
    )
    assert result["sat"] is True
    assert result["status"] == ValidationStatus.PASS.value
    assert result["timeout_ms"] == 5000
    assert 1.0 < result["model"]["x"] < 2.0
    assert "reason" not in result


def test_z3_tool_execute_reports_unsatisfiable_domain() -> None:
    result = z3_tool.Z3Tool().execute(
        {"constraints": ["x > 5"], "variables": {"x": [0.0, 2.0]}}
    )
    assert result == {
        "sat": False,
        "model": None,
        "status": ValidationStatus.FAIL.value,
        "timeout_ms": 10000,
    }


@pytest.mark.parametrize(
    "payload, fragment",
    [
        (None, "payload must be an object"),
        (["not", "a", "dict"], "payload must be an object"),
        ({"variables": {"x": [0, 1]}}, "needs 'constraints'"),
        ({"constraints": []}, "needs 'constraints'"),
        ({"constraints": "x > 1", "variables": {"x": [0, 1]}}, "must be an array"),
        ({"constraints": [], "variables": ["x"]}, "must be an object"),
        ({"constraints": [], "variables": {"x": [0, 1]}, "timeout_ms": True}, "boolean"),
        ({"constraints": [], "variables": {"x": [0, 1]}, "timeout_ms": 0}, "between"),
        (
            {"constraints": [], "variables": {"x": [0, 1]}, "timeout_ms": MAX_Z3_TIMEOUT_MS + 1},
            "between",
        ),
    ],
)
def test_z3_tool_validate_input_rejects_malformed_payloads(payload, fragment) -> None:
    with pytest.raises(ValueError, match=fragment):
        z3_tool.Z3Tool().validate_input(payload)


# ---------------------------------------------------------------------------
# Z3 parser: only the bounded real-arithmetic subset
# ---------------------------------------------------------------------------


def _symbols(**names: str) -> dict[str, object]:
    return {name: z3.Real(symbol) for name, symbol in names.items()}


@pytest.mark.parametrize(
    "expression, symbols, fragment",
    [
        ("~x > 1", {"x": "x"}, "unsupported unary operator: Invert"),
        ("x % 2 > 1", {"x": "x"}, "unsupported binary operator: Mod"),
        ("x is 1", {"x": "x"}, "unsupported comparison operator: Is"),
        ("x > 'a'", {"x": "x"}, "real numeric or boolean constants"),
        ("x > [1, 2]", {"x": "x"}, "unsupported constraint syntax: List"),
        ("x + 1", {"x": "x"}, "must evaluate to a Boolean relation"),
        ("y > 1", {"x": "x"}, "unknown variable in constraint: y"),
        ("foo(x) > 1", {"x": "x"}, r"only And\(\.\.\.\)"),
        ("And(x > 1, key=1)", {"x": "x"}, "keyword arguments are not allowed"),
        ("Not(x > 1, x > 2)", {"x": "x"}, "requires exactly one argument"),
        ("And()", {"x": "x"}, "requires at least one argument"),
        ("x**y > 1", {"x": "x", "y": "y"}, "integer literal exponent"),
        ("x**1.5 > 1", {"x": "x"}, "integer literal exponent"),
        ("x**33 > 1", {"x": "x"}, "integer literal exponent"),
        ("x**-1 > 1", {"x": "x"}, "integer literal exponent"),
        ("x**True > 1", {"x": "x"}, "integer literal exponent"),
    ],
)
def test_z3_parser_rejects_non_contract_syntax(expression, symbols, fragment) -> None:
    scope = {name: z3.Real(real) for name, real in symbols.items()}
    with pytest.raises(ValueError, match=fragment):
        z3_tool._parse_constraint(expression, scope)


@pytest.mark.parametrize("expression", ["", "   ", None, 7])
def test_z3_parser_requires_a_non_empty_string(expression) -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        z3_tool._parse_constraint(expression, {})


def test_z3_parser_rejects_oversized_constraint_text() -> None:
    from axiomize.limits import MAX_EXPRESSION_CHARS

    text = "x" * (MAX_EXPRESSION_CHARS + 1) + " > 1"
    with pytest.raises(ValueError, match="hard limit"):
        z3_tool._parse_constraint(text, {"x": z3.Real("x")})


def test_z3_parser_reports_invalid_python_syntax() -> None:
    with pytest.raises(ValueError, match="invalid Z3 constraint syntax"):
        z3_tool._parse_constraint("x >", {"x": z3.Real("x")})


def test_z3_parser_rejects_excessive_node_count(monkeypatch) -> None:
    monkeypatch.setattr(z3_tool, "MAX_EXPRESSION_NODES", 4)
    with pytest.raises(ValueError, match="AST-node limit"):
        z3_tool._parse_constraint("x + x + x", {"x": z3.Real("x")})


def test_z3_parser_rejects_excessive_nesting_depth(monkeypatch) -> None:
    monkeypatch.setattr(z3_tool, "MAX_EXPRESSION_DEPTH", 2)
    with pytest.raises(ValueError, match="nesting limit"):
        z3_tool._parse_constraint("x + x + x", {"x": z3.Real("x")})


def test_z3_parser_rejects_malformed_comparison_ast(monkeypatch) -> None:
    tree = ast.parse("x > 1", mode="eval")
    tree.body.ops = [ast.Lt(), ast.Gt()]
    tree.body.comparators = [ast.Constant(1)]
    monkeypatch.setattr(ast, "parse", lambda *args, **kwargs: tree)
    with pytest.raises(ValueError, match="malformed comparison"):
        z3_tool._parse_constraint("x > 1", {"x": z3.Real("x")})


def test_z3_parser_accepts_chained_comparisons_as_conjunction() -> None:
    translated = z3_tool._parse_constraint("x < 1 < 2", {"x": z3.Real("x")})
    assert z3.is_bool(translated)
    assert str(translated)


def test_z3_parser_accepts_unary_plus() -> None:
    translated = z3_tool._parse_constraint("+x > 1", {"x": z3.Real("x")})
    assert z3.is_bool(translated)
    solver = z3.Solver()
    solver.add(translated != (z3.Real("x") > 1))
    assert solver.check() == z3.unsat


def test_z3_parser_rejects_unsupported_boolean_operator_ast(monkeypatch) -> None:
    tree = ast.parse("x > 1", mode="eval")
    tree.body = ast.BoolOp(op=ast.Add(), values=[ast.Constant(True)])
    monkeypatch.setattr(ast, "parse", lambda *args, **kwargs: tree)
    with pytest.raises(ValueError, match="unsupported boolean operator: Add"):
        z3_tool._parse_constraint("x > 1", {"x": z3.Real("x")})


def test_z3_algebraic_model_uses_decimal_conversion() -> None:
    result = z3_tool.check_constraints(["x*x == 2"], {"x": (1.0, 2.0)})
    assert result["sat"] is True
    assert result["status"] == ValidationStatus.PASS
    assert result["model"]["x"] == pytest.approx(math.sqrt(2.0))


def test_z3_unknown_verdict_is_reported_as_inconclusive(monkeypatch) -> None:
    class _UnknownSolver:
        def set(self, **kwargs) -> None:
            self.timeout = kwargs.get("timeout")

        def add(self, *constraints) -> None:
            self.constraints = constraints

        def check(self):
            return z3.unknown

        def reason_unknown(self) -> str:
            return "deterministic-unknown-reason"

    monkeypatch.setattr(z3, "Solver", _UnknownSolver)
    result = z3_tool.check_constraints(["x > 1"], {"x": (0.0, 2.0)})
    assert result["sat"] is None
    assert result["model"] is None
    assert result["status"] == ValidationStatus.INCONCLUSIVE
    assert result["reason"] == "deterministic-unknown-reason"


# ---------------------------------------------------------------------------
# Z3 check_constraints input guards
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "constraints, variables, fragment",
    [
        ("x > 1", {"x": [0, 1]}, "constraints must be an array"),
        ([1], {"x": [0, 1]}, "every constraint must be a string"),
        ([], ["x"], "variables must be an object"),
        ([], {}, "variables must contain"),
        (["x > 1"], {"x": [0.0, float("inf")]}, "must be finite"),
        (["x > 1"], {"x": [float("nan"), 1.0]}, "must be finite"),
        (["x > 1"], {"x": ["low", 1.0]}, "lower bound must be numeric"),
        (["x > 1"], {"x": [0.0, None]}, "upper bound must be numeric"),
        (["x > 1"], {"x": [2.0, 1.0]}, "lower bound must be <= upper bound"),
        (["x > 1"], {"x": 0.5}, "must contain \\[low, high\\]"),
        (["x > 1"], {"x": [0.0, 1.0, 2.0]}, "must contain \\[low, high\\]"),
        (["x > 1"], {"x": [0.0, 2.0], "bad name": [0, 1]}, "must start with an ASCII letter"),
    ],
)
def test_z3_check_constraints_fails_closed_on_untrusted_input(
    constraints, variables, fragment
) -> None:
    with pytest.raises(ValueError, match=fragment):
        z3_tool.check_constraints(constraints, variables)


def test_z3_check_constraints_rejects_too_many_constraints() -> None:
    with pytest.raises(ValueError, match="constraints exceed hard limit"):
        z3_tool.check_constraints(["x > 0"] * 10_001, {"x": [0.0, 1.0]})


def test_z3_check_constraints_rejects_too_many_variables() -> None:
    variables = {f"v{index}": (0.0, 1.0) for index in range(2_049)}
    with pytest.raises(ValueError, match="1\\.\\.2048"):
        z3_tool.check_constraints([], variables)


@pytest.mark.parametrize("timeout", [0, True, MAX_Z3_TIMEOUT_MS + 1, "not-an-int"])
def test_z3_check_constraints_validates_timeout(timeout) -> None:
    with pytest.raises(ValueError):
        z3_tool.check_constraints([], {"x": [0.0, 1.0]}, timeout_ms=timeout)


# ---------------------------------------------------------------------------
# Dimensional parser branches
# ---------------------------------------------------------------------------


_DIMS = {"x": {"L": 1.0}, "y": {"L": 1.0}, "t": {"T": 1.0}, "k": {}}


@pytest.mark.parametrize(
    "expression, fragment",
    [
        ("True", "only numeric constants"),
        ("Abs(1, 2)", "Abs expects one argument"),
        ("sqrt(x, y)", "sqrt expects one argument"),
        ("Min()", "arguments must have equal dimensions"),
        ("Max()", "arguments must have equal dimensions"),
        ("x > 1", "unsupported syntax Compare"),
        ("x if k else y", "unsupported expression syntax"),
    ],
)
def test_dimension_parser_rejects_unsupported_shape(expression, fragment) -> None:
    with pytest.raises(ValueError, match=fragment):
        dimension._parse_dimension(expression, _DIMS)


def test_dimension_parser_accepts_all_zero_exponent_cancellation() -> None:
    assert dimension._parse_dimension("(x/x)**0", _DIMS) == {}
    assert dimension._parse_dimension("k*0", _DIMS) == {}


def test_dimension_parser_rejects_unknown_symbol_after_namespace_bypass(monkeypatch) -> None:
    monkeypatch.setattr(dimension, "validate_expression", lambda *args, **kwargs: ast.parse("z", mode="eval"))
    with pytest.raises(ValueError, match="unknown symbol 'z'"):
        dimension._parse_dimension("z", {})


def test_dimension_parser_rejects_unsupported_binary_operator_ast(monkeypatch) -> None:
    monkeypatch.setattr(
        dimension, "validate_expression", lambda *args, **kwargs: ast.parse("x @ y", mode="eval")
    )
    with pytest.raises(ValueError, match="unsupported operator MatMult"):
        dimension._parse_dimension("x @ y", _DIMS)


def test_dimension_parser_rejects_unsupported_call_after_namespace_bypass(monkeypatch) -> None:
    monkeypatch.setattr(
        dimension, "validate_expression", lambda *args, **kwargs: ast.parse("gamma(x)", mode="eval")
    )
    with pytest.raises(ValueError, match="unsupported function in dimensional expression"):
        dimension._parse_dimension("gamma(x)", _DIMS)


def test_bayesian_data_symbol_already_declared_is_not_overwritten() -> None:
    model = _model(
        family=ModelFamily.BAYESIAN,
        variables=[VariableSpec(name="x", unit="dimensionless")],
        equations=[EquationSpec(target="", expression="x - x", kind="residual")],
        metadata={"bayesian": {"data": {"x": [1.0, 2.0]}}},
    )
    checks = dimension.equation_dimension_checks(model)
    assert checks[0]["status"] == "UNVERIFIED"
    assert "{}" in checks[0]["detail"]


# ---------------------------------------------------------------------------
# Advanced symbol registration in equation checks
# ---------------------------------------------------------------------------


def _model(
    *,
    family: ModelFamily,
    variables: list[VariableSpec],
    parameters: list[ParameterSpec] | None = None,
    equations: list[EquationSpec] | None = None,
    independent_variable: str = "t",
    independent_unit: str = "day",
    metadata: dict | None = None,
) -> ModelIR:
    return ModelIR(
        name="dimension-probe",
        domain="test",
        family=family,
        variables=variables,
        parameters=list(parameters or []),
        equations=list(equations or []),
        independent_variable=independent_variable,
        independent_unit=independent_unit,
        metadata=dict(metadata or {}),
    )


def test_network_family_registers_generated_neighbor_symbols() -> None:
    model = _model(
        family=ModelFamily.NETWORK,
        variables=[VariableSpec(name="x", unit="1/day", initial=1.0)],
        equations=[EquationSpec(target="", expression="neighbor_x_sum - degree*x", kind="residual")],
    )
    checks = dimension.equation_dimension_checks(model)
    assert checks[0]["status"] == "UNVERIFIED"
    assert "expression_dimension" in checks[0]["detail"]
    assert "residual/objective" in checks[0]["detail"]


def test_agent_based_family_registers_only_mean_symbol() -> None:
    model = _model(
        family=ModelFamily.AGENT_BASED,
        variables=[VariableSpec(name="x", unit="dimensionless", initial=1.0)],
        equations=[EquationSpec(target="", expression="mean_x - x", kind="residual")],
    )
    checks = dimension.equation_dimension_checks(model)
    assert checks[0]["status"] == "UNVERIFIED"
    assert "{}" in checks[0]["detail"]


def test_metadata_symbol_units_are_registered_with_exact_dimensions() -> None:
    model = _model(
        family=ModelFamily.ALGEBRAIC,
        variables=[VariableSpec(name="x", unit="dimensionless")],
        equations=[EquationSpec(target="", expression="z*t - x", kind="residual")],
        metadata={"symbol_units": {"z": "1/day"}},
    )
    checks = dimension.equation_dimension_checks(model)
    assert checks[0]["status"] == "UNVERIFIED"
    assert "expression_dimension" in checks[0]["detail"]


def test_bayesian_data_symbols_default_to_dimensionless_without_unit_map() -> None:
    model = _model(
        family=ModelFamily.BAYESIAN,
        variables=[VariableSpec(name="x", unit="dimensionless")],
        equations=[EquationSpec(target="", expression="obs - x", kind="residual")],
        metadata={"bayesian": {"data": {"obs": [1.0, 2.0]}, "data_units": "not-a-map"}},
    )
    checks = dimension.equation_dimension_checks(model)
    assert checks[0]["status"] == "UNVERIFIED"
    assert "{}" in checks[0]["detail"]


def test_bayesian_data_symbols_use_declared_units() -> None:
    model = _model(
        family=ModelFamily.BAYESIAN,
        variables=[VariableSpec(name="x", unit="1/day")],
        equations=[EquationSpec(target="", expression="obs - x", kind="residual")],
        metadata={
            "bayesian": {
                "data": {"obs": [1.0, 2.0]},
                "data_units": {"obs": "1/day"},
            }
        },
    )
    checks = dimension.equation_dimension_checks(model)
    assert checks[0]["status"] == "UNVERIFIED"
    assert "expression_dimension" in checks[0]["detail"]


def test_declared_equation_unit_sets_the_expected_basis() -> None:
    model = _model(
        family=ModelFamily.ALGEBRAIC,
        variables=[VariableSpec(name="x", unit="dimensionless")],
        parameters=[ParameterSpec(name="k", unit="dimensionless", value=1.0)],
        equations=[
            EquationSpec(target="res", expression="x - k", kind="residual", unit="dimensionless")
        ],
    )
    checks = dimension.equation_dimension_checks(model)
    assert checks[0]["status"] == "PASS"
    assert "declared unit dimensionless" in checks[0]["detail"]


def test_derivative_of_unknown_target_is_a_visible_failure() -> None:
    model = _model(
        family=ModelFamily.ODE,
        variables=[VariableSpec(name="x", unit="dimensionless", initial=1.0)],
        equations=[EquationSpec(target="ghost", expression="1", kind="derivative")],
    )
    checks = dimension.equation_dimension_checks(model)
    assert checks[0]["status"] == "FAIL"
    assert "unknown derivative target" in checks[0]["detail"]


def test_algebraic_unknown_target_is_a_visible_failure() -> None:
    model = _model(
        family=ModelFamily.ALGEBRAIC,
        variables=[VariableSpec(name="x", unit="dimensionless")],
        equations=[EquationSpec(target="ghost", expression="1", kind="algebraic")],
    )
    checks = dimension.equation_dimension_checks(model)
    assert checks[0]["status"] == "FAIL"
    assert "unknown target" in checks[0]["detail"]


def test_dimension_mismatch_is_a_visible_failure() -> None:
    model = _model(
        family=ModelFamily.ODE,
        variables=[VariableSpec(name="x", unit="1/day", initial=1.0)],
        equations=[EquationSpec(target="x", expression="1", kind="derivative")],
    )
    checks = dimension.equation_dimension_checks(model)
    assert checks[0]["status"] == "FAIL"
    assert "actual={}" in checks[0]["detail"]


def test_unparseable_equation_is_recorded_not_raised() -> None:
    model = _model(
        family=ModelFamily.ALGEBRAIC,
        variables=[VariableSpec(name="x", unit="dimensionless")],
        equations=[EquationSpec(target="", expression="bogus + 1", kind="residual")],
    )
    checks = dimension.equation_dimension_checks(model)
    assert checks[0]["status"] == "FAIL"
    assert checks[0]["detail"].startswith("ValueError:")


def test_merge_dimension_checks_appends_pass_checks_without_changing_status() -> None:
    model = _model(
        family=ModelFamily.ALGEBRAIC,
        variables=[VariableSpec(name="x", unit="dimensionless")],
        equations=[EquationSpec(target="", expression="x - x", kind="residual")],
    )
    merged = dimension.merge_dimension_checks(
        {"status": "PASS", "checks": [{"name": "structure", "status": "PASS"}]}, model
    )
    assert merged["status"] == "PASS"
    assert [check["name"] for check in merged["checks"]] == ["structure", "equation_dimension:0"]
    assert merged["equation_dimension_checks"] == merged["checks"][1:]


def test_merge_dimension_checks_turns_engine_crash_into_fail_closed_status() -> None:
    broken = SimpleNamespace(
        variables=[SimpleNamespace(name="x", unit=object())],
        parameters=[],
        independent_variable="t",
        independent_unit="day",
        equations=[],
        family=ModelFamily.ALGEBRAIC,
        metadata={},
    )
    merged = dimension.merge_dimension_checks({"status": "PASS"}, broken)
    assert merged["status"] == "FAIL"
    assert merged["equation_dimension_checks"] == [
        {
            "name": "equation_dimension_engine",
            "status": "FAIL",
            "detail": merged["equation_dimension_checks"][0]["detail"],
        }
    ]
    assert merged["equation_dimension_checks"][0]["detail"].startswith("DimensionalMismatch:")
