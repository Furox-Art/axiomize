"""Regression tests for the bundled axiomize tools.

Run with: pytest tests/ -v
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

# Make the skill tools importable without installing the package
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "skills" / "axiomize" / "tools"))

from csv_check import load  # noqa: E402
from fit import fit_logistic, fit_sir  # noqa: E402
from report_to_latex import convert, neutralize_dangerous_macros  # noqa: E402
from validate import final_size_theory, run_sir  # noqa: E402


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sir_csv(tmp_path):
    """A small deterministic SIR-like infected-count series."""
    t = np.arange(0, 30, 2, dtype=float)
    y = 10 * np.exp(0.15 * t)
    p = tmp_path / "sir.csv"
    p.write_text("day,infected\n" + "\n".join(f"{ti:.0f},{yi:.2f}" for ti, yi in zip(t, y)))
    return p


@pytest.fixture
def ideas_json():
    return json.loads((REPO / "benchmarks" / "ideas.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# validate.py
# ---------------------------------------------------------------------------


class TestValidate:
    def test_final_size_theory_supercritical(self):
        # R0 = 2.0 -> final size ~ 0.7968
        z = final_size_theory(0.3, 0.15)
        assert 0.79 < z < 0.80

    def test_final_size_theory_subcritical(self):
        # R0 = 0.5 -> no outbreak, final size 0
        assert final_size_theory(0.05, 0.1) == 0.0

    def test_final_size_theory_critical(self):
        # R0 = 1.0 -> no outbreak, final size 0
        assert final_size_theory(0.1, 0.1) == 0.0

    def test_run_sir_respects_days(self):
        sol_short = run_sir(0.3, 0.1, 10, 1_000_000, days=30)
        sol_long = run_sir(0.3, 0.1, 10, 1_000_000, days=365)
        assert sol_short.t[-1] == 30.0
        assert sol_long.t[-1] == 365.0
        # Longer horizon -> larger final size for an outbreak
        assert sol_long.y[2][-1] > sol_short.y[2][-1]

    def test_run_sir_population_conserved(self):
        sol = run_sir(0.3, 0.1, 10, 1_000_000, days=180)
        total = sol.y[0] + sol.y[1] + sol.y[2]
        assert np.allclose(total, 1_000_000, atol=1e-3)


# ---------------------------------------------------------------------------
# fit.py
# ---------------------------------------------------------------------------


class TestFit:
    def test_fit_sir_requires_n(self):
        t = np.linspace(0, 30, 15)
        y = 10 * np.exp(0.15 * t)
        with pytest.raises(ValueError):
            fit_sir(t, y)

    def test_fit_sir_recovers_truth(self):
        rng = np.random.default_rng(7)
        t = np.linspace(0, 60, 25)
        N, I0, beta, gamma = 10000, 20, 0.35, 0.12

        def rhs(_, y):
            S, I, _R = y
            return [-beta * S * I / N, beta * S * I / N - gamma * I, gamma * I]

        from scipy.integrate import solve_ivp
        clean = solve_ivp(rhs, (0, 60), [N - I0, float(I0), 0.0], t_eval=t).y[1]
        noisy = clean * (1 + rng.normal(0, 0.03, size=len(t)))
        res = fit_sir(t, noisy, N=N)
        b_hat = res["params"]["beta"][0]
        g_hat = res["params"]["gamma"][0]
        assert abs(b_hat - beta) / beta < 0.15
        assert abs(g_hat - gamma) / gamma < 0.15

    def test_fit_logistic_recovers_truth(self):
        rng = np.random.default_rng(11)
        t = np.linspace(0, 30, 22)
        r, K, y0 = 0.4, 5000.0, 40.0
        clean = K / (1 + (K / y0 - 1) * np.exp(-r * t))
        noisy = clean * (1 + rng.normal(0, 0.02, size=len(t)))
        res = fit_logistic(t, noisy)
        assert abs(res["params"]["r"][0] - r) / r < 0.15
        assert abs(res["params"]["K"][0] - K) / K < 0.05


# ---------------------------------------------------------------------------
# csv_check.py
# ---------------------------------------------------------------------------


class TestCsvCheck:
    def test_load_requires_explicit_columns(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("time,value\n1,10\n2,20\n")
        with pytest.raises(SystemExit):
            load(str(p), None, None)

    def test_load_rejects_wrong_column_name(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("time,value\n1,10\n2,20\n")
        with pytest.raises(SystemExit):
            load(str(p), "timestamp", "value")

    def test_load_accepts_correct_columns(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("time,value\n1,10\n2,20\n")
        tname, vname, t, y = load(str(p), "time", "value")
        assert tname == "time"
        assert vname == "value"
        assert len(t) == 2

    def test_load_does_not_sort_unsorted_input(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("time,value\n3,30\n1,10\n2,20\n")
        tname, vname, t, y = load(str(p), "time", "value")
        # Must return in file order, not sorted
        assert list(t) == [3.0, 1.0, 2.0]
        assert list(y) == [30.0, 10.0, 20.0]


# ---------------------------------------------------------------------------
# report_to_latex.py
# ---------------------------------------------------------------------------


class TestReportToLatex:
    def test_neutralize_dangerous_macros(self):
        dropped = set()
        result = neutralize_dangerous_macros(r"\input{/etc/passwd}", dropped)
        assert r"\input" not in result
        assert "blocked" in result
        assert any("input" in d for d in dropped)

    def test_convert_blocks_input_in_math(self):
        md = r"$$\input{evil}$$"
        tex = convert(md)
        assert r"\input" not in tex

    def test_convert_escapes_input_in_text(self):
        md = r"Text with \input{evil} outside math."
        tex = convert(md)
        assert r"\input" not in tex
        assert r"\textbackslash" in tex

    def test_convert_blocks_include(self):
        md = r"$$\include{secret}$$"
        tex = convert(md)
        assert r"\include" not in tex


# ---------------------------------------------------------------------------
# benchmark_runner.py (gate behavior)
# ---------------------------------------------------------------------------


class TestBenchmarkGate:
    def test_all_cases_have_unique_ids(self, ideas_json):
        ids = [c["id"] for c in ideas_json["cases"]]
        assert len(ids) == len(set(ids))

    def test_all_cases_have_required_keys(self, ideas_json):
        required = {"id", "prompt", "must_contain", "expected_archetype", "min_lenses_built"}
        for case in ideas_json["cases"]:
            missing = required - set(case.keys())
            assert not missing, f"case {case.get('id')} missing {missing}"

    def test_case_count_is_10(self, ideas_json):
        # CI runs exactly this many cases; if a case is silently dropped the
        # count stays at 8 and the regression goes unnoticed.
        assert len(ideas_json["cases"]) == 10
