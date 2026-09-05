"""PHASE 1 engine tests: dimensions, symbolic, numerical, routing, sandbox, run-state."""

import json
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from axiomize.execution.sandbox import UnsafeExecutionDenied, run_python
from axiomize.routing.router import classify
from axiomize.runs.state import RunState
from axiomize.tools.numerical.scipy_tool import final_size_numeric, solve_sir
from axiomize.tools.symbolic.sympy_tool import check_equivalence, differentiate, final_size_symbolic, simplify_expr
from axiomize.validation.dimensions import Dimension, DimensionalMismatch, Quantity, check_add
from axiomize.validation.status import ValidationStatus


class TestDimensions:
    def test_same_units_add_ok(self):
        a = Quantity("length_a", "a", "metre", value=1.0)
        b = Quantity("length_b", "b", "metre", value=2.0)
        assert check_add(a, b).status == ValidationStatus.PASS

    def test_metre_plus_second_fails(self):
        a = Quantity("length", "L", "metre", value=1.0)
        b = Quantity("time", "t", "second", value=1.0)
        with pytest.raises(DimensionalMismatch):
            check_add(a, b)

    def test_dimensionless_must_be_explicit(self):
        with pytest.raises(DimensionalMismatch):
            Quantity("ratio", "r", "", value=1.0)

    def test_multiply_combines_dimensions(self):
        beta = Quantity("transmission rate", "beta", "1/day", value=0.3)
        days = Quantity("horizon", "T", "day", value=10.0)
        assert (beta.dimension * days.dimension) == Dimension({})

    def test_valid_range_violation_warns(self):
        q = Quantity("probability", "p", "dimensionless", value=7.0, valid_range=(0.0, 1.0))
        assert q.range_check().status == ValidationStatus.FAIL


class TestSymbolic:
    def test_simplify_known_identity(self):
        assert simplify_expr("(x + 1)**2 - x**2 - 2*x - 1") == "0"

    def test_derivative_of_exp_decay(self):
        assert differentiate("exp(-gamma*t)", "t") == "-gamma*exp(-gamma*t)"

    def test_wrong_equation_not_equivalent(self):
        assert check_equivalence("beta + gamma", "beta/gamma") is False
        assert check_equivalence("beta/gamma", "beta*gamma**(-1)") is True

    def test_final_size_symbolic_matches_theory(self):
        z = final_size_symbolic(3.0)
        assert abs(z - 0.9404798) < 1e-4

    def test_final_size_subcritical_is_zero(self):
        assert final_size_symbolic(0.5) == 0.0


class TestNumerical:
    def test_sir_solution_conserves_population(self):
        res = solve_sir(beta=0.3, gamma=0.1, I0=10, N=1_000_000, days=180)
        assert res.success is True
        assert res.max_conservation_error < 1e-3

    def test_sir_residual_is_small(self):
        res = solve_sir(beta=0.3, gamma=0.1, I0=10, N=1_000_000, days=180)
        assert res.max_residual < 1e-4

    def test_solver_agreement_two_methods(self):
        a = solve_sir(beta=0.3, gamma=0.1, I0=10, N=1_000_000, days=180, method="RK45")
        b = solve_sir(beta=0.3, gamma=0.1, I0=10, N=1_000_000, days=180, method="Radau")
        assert abs(a.final_size - b.final_size) < 1e-3

    def test_numeric_final_size_matches_theory(self):
        assert abs(final_size_numeric(0.3, 0.1) - 0.9404798) < 1e-4

    def test_symbolic_numeric_cross_validation(self):
        num = final_size_numeric(0.3, 0.1)
        sym = final_size_symbolic(0.3 / 0.1)
        assert abs(num - sym) < 1e-4


class TestRouter:
    def test_sir_problem_selects_scipy_with_sympy_verification(self):
        problem = {"signals": ["ode", "compartmental", "threshold"], "equations": ["dS/dt = -beta*S*I/N"]}
        d = classify(problem)
        assert "scipy" in d.primary_tools
        assert "sympy" in d.verification_tools
        assert d.problem_type != "unknown"

    def test_decision_schema_has_required_keys(self):
        d = classify({"signals": ["ode"]})
        payload = d.to_dict()
        assert set(payload) >= {"problem_type", "primary_tools", "verification_tools", "reason", "alternatives"}

    def test_unavailable_tool_never_selected(self):
        d = classify({"signals": ["pde", "fem"]})
        assert "fenics" not in d.primary_tools
        assert d.status == ValidationStatus.TOOL_UNAVAILABLE or d.primary_tools != ["fenics"]

    def test_unknown_problem_is_explicit(self):
        d = classify({"signals": ["telepathy"]})
        assert d.problem_type == "unknown"
        assert d.status == ValidationStatus.INCONCLUSIVE


class TestSandbox:
    def test_arbitrary_execution_denied_by_default(self):
        with pytest.raises(UnsafeExecutionDenied):
            run_python("print(6 * 7)", timeout_s=30)

    def test_captured_stdout(self):
        rec = run_python("print(6 * 7)", timeout_s=30, allow_unsafe_code=True)
        assert rec.exit_code == 0
        assert rec.stdout.strip() == "42"

    def test_timeout_kills(self):
        rec = run_python("import time; time.sleep(60)", timeout_s=2, allow_unsafe_code=True)
        assert rec.timed_out is True
        assert rec.exit_code != 0

    def test_stderr_and_seed_recorded(self):
        rec = run_python("import sys; print('oops', file=sys.stderr); raise SystemExit(3)",
                         timeout_s=30, seed=123, allow_unsafe_code=True)
        assert rec.exit_code == 3
        assert "oops" in rec.stderr
        assert rec.seed == 123
        assert rec.execution_time_s >= 0.0

    def test_record_has_tool_versions(self):
        rec = run_python("print('hi')", timeout_s=30, allow_unsafe_code=True)
        assert "numpy" in rec.tool_versions
        assert rec.execution_time_s >= 0.0

    def test_environment_secrets_are_not_inherited(self, monkeypatch):
        monkeypatch.setenv("AXIOMIZE_TEST_SECRET", "do-not-leak")
        rec = run_python(
            "import os; print(os.environ.get('AXIOMIZE_TEST_SECRET', 'missing'))",
            timeout_s=30,
            allow_unsafe_code=True,
        )
        assert rec.stdout.strip() == "missing"
        assert rec.environment_inherited is False


class TestRunState:
    def test_save_and_reload_roundtrip(self, tmp_path):
        run = RunState(problem_definition="SIR test", solver_settings={"tol": 1e-8})
        run.add_result("final_size", 0.9404)
        d = tmp_path / "run001"
        run.save(d)
        assert (d / "run.json").is_file()
        assert (d / "manifest.json").is_file()
        loaded = RunState.load(d)
        assert loaded.results["final_size"] == 0.9404
        assert loaded.problem_definition == "SIR test"

    def test_reproduce_same_inputs_same_hash(self, tmp_path):
        kwargs = {"problem_definition": "SIR test", "equations": ["dS/dt=-beta*S*I/N"], "parameters": {"beta": 0.3}}
        a = RunState(**kwargs); b = RunState(**kwargs)
        assert a.input_hash() == b.input_hash()

    def test_manifest_records_versions(self, tmp_path):
        run = RunState(problem_definition="x")
        d = tmp_path / "run002"
        run.save(d)
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        assert "axiomize_version" in manifest
        assert "tool_versions" in manifest
        assert "timestamp" in manifest
        assert "run_sha256" in manifest
        assert math.prod([1]) == 1
