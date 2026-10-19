"""Execute shipped numerical benchmark cases and verify evidence-driven verdicts."""

from __future__ import annotations

import pytest

from axiomize import benchmark_suite


@pytest.mark.parametrize("case_name", [
    "deterministic_model",
    "nonlinear_ode_outbreak",
    "regression",
    "control_problem",
    "missing_information_explicit",
])
def test_native_science_benchmark_with_real_numerical_execution(case_name):
    cases = dict(benchmark_suite._CASES)
    cases[case_name]()


def test_benchmark_reports_an_actual_exception_instead_of_hiding_it(monkeypatch):
    def successful():
        return None

    def unsuccessful():
        raise ValueError("deliberately corrupted benchmark evidence")

    monkeypatch.setattr(benchmark_suite, "_CASES", [
        ("valid_result", successful),
        ("corrupt_result", unsuccessful),
    ])
    result = benchmark_suite.run_suite()
    assert result["status"] == "FAIL"
    assert (result["passed"], result["total"]) == (1, 2)
    assert result["results"][0] == {"name": "valid_result", "status": "PASS"}
    assert result["results"][1]["status"] == "FAIL"
    assert "ValueError" in result["results"][1]["error"]
    assert "corrupted benchmark evidence" in result["results"][1]["traceback"]


def test_every_successful_report_is_attributed_to_a_real_case(monkeypatch):
    recorded = []

    def complete_case():
        recorded.append("executed")

    monkeypatch.setattr(benchmark_suite, "_CASES", [
        ("grounded_run", complete_case),
    ])
    report = benchmark_suite.run_suite()
    assert report["status"] == "PASS"
    assert (report["passed"], report["total"]) == (1, 1)
    assert report["results"] == [{"name": "grounded_run", "status": "PASS"}]
    assert recorded == ["executed"]
