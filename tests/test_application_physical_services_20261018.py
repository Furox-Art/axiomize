"""Direct SIR, fitting, confidence and policy contracts across applications."""
from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.application import services as service


@pytest.mark.parametrize("invalid,reason", [
    ({"beta": -1}, "beta"), ({"gamma": 0}, "gamma"),
    ({"N": -1}, "population"), ({"I0": -1}, "I0"),
    ({"N": 100, "I0": 101}, "I0"), ({"days": 0}, "days"),
    ({"beta": float("nan")}, "finite"),
    ({"gamma": "invalid"}, "numeric"),
])
def test_physical_sir_inputs_cannot_be_accepted_as_predictions(invalid, reason):
    with pytest.raises(ValueError, match=reason):
        service._sir_parameters(invalid)


def test_physical_default_parameters_are_finite_and_ordered():
    beta, gamma, i0, population, days = service._sir_parameters({})
    assert 0 <= i0 <= population
    assert gamma > 0
    assert beta >= 0
    assert days > 0


@pytest.mark.parametrize("beta,gamma,i0,n,expected", [
    (0.3, 0.1, 0, 1000, 0),
    (0.3, 0.1, 1000, 1000, 1),
    (0, 0.1, 10, 1000, 0.01),
])
def test_two_independent_final_size_formulas_agree_on_exact_edges(beta, gamma, i0, n, expected):
    assert service._sir_asymptotic_final_size_numeric(beta, gamma, i0, n) == pytest.approx(expected)
    assert service._sir_asymptotic_final_size_symbolic(beta, gamma, i0, n) == pytest.approx(expected)


@pytest.mark.parametrize("beta,gamma,i0,n", [
    (0.3, 0.1, 10, 1000),
    (0.05, 0.1, 1, 1000),
    (0.5, 0.1, 1, 200),
])
def test_numeric_brent_and_symbolic_lambert_w_are_consistent(beta, gamma, i0, n):
    numeric = service._sir_asymptotic_final_size_numeric(beta, gamma, i0, n)
    symbolic = service._sir_asymptotic_final_size_symbolic(beta, gamma, i0, n)
    assert 0 <= numeric <= 1
    assert numeric == pytest.approx(symbolic, abs=1e-8)


def test_real_sir_solution_preserves_horizon_uncertainty():
    result = service.solve_sir_service({
        "beta": 0.3, "gamma": 0.1, "I0": 10, "N": 1000, "days": 2,
    })
    assert result["status"] == "PASS"
    assert result["finite_horizon_converged"] is False
    assert result["numeric_theory_check"]["status"] == "INCONCLUSIVE"
    assert result["cross_validation"]["status"] == "PASS"
    assert result["max_conservation_error"] < 1e-3


def test_real_sir_final_horizon_convergence_gets_independent_comparison():
    result = service.solve_sir_service({
        "beta": 0.0, "gamma": 0.5, "I0": 10, "N": 1000, "days": 60,
    })
    assert result["status"] == "PASS"
    assert result["finite_horizon_converged"] is True
    assert result["numeric_theory_check"]["status"] == "PASS"
    assert result["asymptotic_final_size"] == pytest.approx(0.01)


def test_full_sir_validation_reports_all_direct_constraints():
    result = service.validate_sir_service({"beta": 0.2, "gamma": 0.1, "I0": 10, "N": 1000, "days": 120})
    assert result["status"] == "PASS"
    assert result["validation_checks"] and all(result["validation_checks"].values())


@pytest.mark.parametrize("value,reason", [
    ({"t": [0, 1], "y": [1, 2, 3]}, "same length"),
    ({"t": [0, float("nan")], "y": [1, 2]}, "finite"),
    ({"t": [0, 1], "y": [1, float("inf")]}, "finite"),
])
def test_empirical_time_series_rejects_invalid_alignment(value, reason):
    with pytest.raises(ValueError, match=reason):
        service._xy(value)


def test_logistic_curve_is_fitted_from_real_samples():
    t = np.linspace(0, 10, 35)
    y = 15.0 / (1.0 + np.exp(-0.9 * (t - 5.0)))
    result = service.fit_logistic_service({"t": t.tolist(), "y": y.tolist()})
    assert result["success"] is True
    assert math.isfinite(result["K"])


def test_fit_comparison_uses_available_model_without_inventing_missing_population():
    t = np.linspace(0, 8, 30)
    y = 12 / (1 + np.exp(-0.6 * (t - 4)))
    result = service.compare_service({"t": t.tolist(), "y": y.tolist()})
    assert "logistic" in result["fits"]
    assert "sir" not in result["fits"]


@pytest.mark.parametrize("payload", [
    {"target": "not-supported", "params": {"beta": 0.3, "gamma": 0.1}},
    {"params": {}},
    {"params": {"beta": 0.3}},
])
def test_sensitivity_scans_refuse_unknown_target_or_absent_rates(payload):
    with pytest.raises(ValueError):
        service.sensitivity_service(payload)


def test_missing_fit_uncertainty_is_never_fabricated():
    result = service.uncertainty_service({})
    assert result["status"] == "UNVERIFIED"
    assert result["intervals"] == {}


@pytest.mark.parametrize("params", [
    {"beta": [1.0, -0.3]},
    {"beta": [1.0, float("inf")]},
    {"beta": "corrupt"},
    {"beta": {"value": 1.0}},
])
def test_invalid_uncertainty_rows_have_explicit_unverified_status(params):
    result = service.uncertainty_service({"params": params})
    assert result["status"] == "UNVERIFIED"
    assert result["intervals"] == {}


def test_real_normal_confidence_interval_respects_reported_standard_error():
    result = service.uncertainty_service({"params": {
        "beta": [0.5, 0.1],
        "gamma": {"value": 0.1, "stderr": 0.02},
    }})
    assert result["status"] == "PASS"
    assert result["uncertainty"]["n_params"] == 2
    assert result["intervals"]["beta"][0] == pytest.approx(0.3040036, abs=1e-4)
    assert result["intervals"]["gamma"][1] > 0.1


def test_workflow_policy_rejects_unstructured_permissions():
    with pytest.raises(ValueError, match="permissions must be an object"):
        service.workflow_policy_service({"permissions": [1, 2]})


def test_workflow_default_keeps_expensive_operations_approval_gated():
    result = service.workflow_policy_service()
    assert result["policy"]["permissions"]["allow_spawn_subtasks"] is False
    assert result["rigor_recommendation"]


def test_clean_data_refuses_missing_pairs_and_preserves_audit():
    with pytest.raises(ValueError, match="requires t and y"):
        service.clean_data_service({"t": [0, 1]})
    result = service.clean_data_service({"t": [1, 0, 1], "y": [3, 1, 5]})
    assert result["cleaned_t"] == [0.0, 1.0]
    assert result["cleaned_y"] == [1.0, 4.0]
    assert result["audit"]


@pytest.mark.parametrize("record", [{}, {"before_dir": "one"}, {"after_dir": "two"}])
def test_run_comparison_requires_two_reproducible_run_ids(record):
    with pytest.raises(ValueError, match="before_dir and after_dir"):
        service.compare_runs_service(record)


def test_observed_falsifier_is_an_actual_failure_not_an_unsupported_inference():
    outcome = service.falsify_service({
        "falsifiers": [{
            "name": "peak infection", "observable": "I",
            "threshold": 10.0, "direction": "above",
        }],
        "observations": {"I": 11.0},
    })
    assert outcome["model_status"] == "FAIL"
    assert len(outcome["results"]) == 1
    assert outcome["results"][0]["triggered"] is True
    assert outcome["untested"] == []


def test_absent_falsification_measurement_is_kept_untested():
    outcome = service.falsify_service({
        "falsifiers": [{
            "name": "required measurement", "observable": "missing",
            "threshold": 1.0, "direction": "below",
        }], "observations": {},
    })
    assert outcome["untested"]
    assert outcome["model_status"] != "PASS"


@pytest.mark.parametrize("falsifiers", [
    None, "untrusted", {"f": 1}, [None] * 10001,
])
def test_falsifier_list_cannot_be_guessed_or_unbounded(falsifiers):
    with pytest.raises(ValueError, match="falsifiers"):
        service.falsify_service({"falsifiers": falsifiers})


def test_nonfinite_falsification_threshold_is_explicitly_rejected():
    with pytest.raises(ValueError, match="finite"):
        service.falsify_service({"falsifiers": [{
            "name": "bad", "observable": "y",
            "threshold": float("nan"),
        }]})


def test_scientific_tool_inventory_reports_actual_availability():
    inventory = service.tools_service()
    assert "tools" in inventory
    assert "scipy" in inventory["tools"]
    assert inventory["tools"]["scipy"]["available"] is True


def test_capabilities_disclose_true_approval_gates_and_ir_families():
    meta = service.capabilities_service()
    assert meta["model_ir"]["migration_requires_approval"] is True
    assert "ir_migration" in meta["consumption_guard"]["guarded_actions"]


def test_intake_requires_actual_scientific_model_scope():
    result = service.intake_service({"idea": "physical decay of a molecule"})
    assert result["status"] == "NEEDS_INPUT"
    assert result["questions"]
    assert result["policy"]["permissions"]["allow_heavy_compute"] is False


def test_nested_fit_uncertainty_is_recognized_without_fabricated_parameters():
    result = service.uncertainty_service({"fit": {
        "params": {"beta": {"value": 0.3, "stderr": 0.02}},
    }})
    assert result["status"] == "PASS"
    assert result["uncertainty"]["n_params"] == 1


def test_empty_observations_do_not_generate_falsification_pass():
    outcome = service.falsify_service({"falsifiers": [], "observations": {}})
    assert outcome["results"] == []
    assert outcome["model_status"] != "PASS"


def test_reproducible_saved_run_comparison_surfaces_input_change(tmp_path):
    from axiomize.runs.state import RunState

    before = tmp_path / "before"
    after = tmp_path / "after"
    RunState(parameters={"beta": 0.3}, results={"peak": 1.0}).save(before)
    RunState(parameters={"beta": 0.4}, results={"peak": 2.0}).save(after)
    actual = service.compare_runs_service({
        "before_dir": str(before), "after_dir": str(after),
    })
    assert actual["same_input_hash"] is False
    assert actual["differences"]["parameters"]["beta"] == {
        "before": 0.3, "after": 0.4,
    }


@pytest.mark.parametrize("sample,fragment", [
    ({"params": {"beta": {"value": float("nan"), "stderr": 1}}}, "UNVERIFIED"),
    ({"params": {"beta": [1.0, -1.0]}}, "UNVERIFIED"),
])
def test_unreliable_fit_confidence_never_becomes_pass(sample, fragment):
    assert service.uncertainty_service(sample)["status"] == fragment


@pytest.mark.parametrize("target", ["final_size", "peak_infected"])
def test_real_bounded_parameter_sensitivity_runs_local_and_monte_carlo(target):
    # 1,000 seeded evaluations are executed by the production scientific
    # engines. Verify the result numerically; no proxy-only fit is accepted.
    result = service.sensitivity_service({
        "params": {"beta": 0.3, "gamma": 0.1},
        "I0": 1.0, "N": 2000.0,
        "target": target,
    })
    assert set(result["local"]) == {"beta", "gamma"}
    assert set(result["mc_screening"]) == {"beta", "gamma"}
    assert all(math.isfinite(v) for v in result["local"].values())
    assert all(0.0 <= v <= 1.0 for v in result["mc_screening"].values())
    assert sum(result["mc_screening"].values()) == pytest.approx(1.0, abs=1e-12)
