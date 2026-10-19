"""Verify genuine refinement approval and fail-closed scientific error telemetry.

The failure-injection callbacks check structure and refusal, not claimed solver
accuracy. Positive ODE and PDE integration remains covered separately.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize import numerical_verification as verify
from axiomize import scientific_stress
from axiomize.model_ir import ModelFamily


def model(family):
    return scientific_stress._models()[family]


def study(ir, responder=None, *, approve_heavy=True, **kwargs):
    if responder is None:
        def responder(*args, **kwargs):
            raise AssertionError("model execution not approved")
    return verify.numerical_refinement_study(
        ir, simulate_once=responder, t_span=(0.0, 1.0),
        points=10, approve_heavy=approve_heavy, **kwargs,
    )


def pde_snapshot(ir, **kwargs):
    grid = int(ir.metadata["pde"]["grid_points"])
    x = np.linspace(0.0, 1.0, grid)
    return {
        "status": "PASS",
        "coordinates": {"x": x.tolist()},
        "states": {"u": np.ones((10, grid)).tolist()},
        "diagnostics": {"dx": float(x[1] - x[0])},
        "solver": {"method": "controlled constant-field fixture"},
    }


def test_direct_difference_rejects_mismatched_scientific_array_shapes():
    with pytest.raises(ValueError, match="shape mismatch"):
        verify._relative_errors(np.ones(10), np.ones(11))


def test_direct_difference_has_zero_error_for_identical_observations():
    assert verify._relative_errors(np.ones(10), np.ones(10)) == (0.0, 0.0, 0.0)


@pytest.mark.parametrize("errors,ratios", [
    ([], []), ([0.1], [2.0]), ([0.1, 0.05], []),
    ([0.0, 0.05], [2.0]), ([0.1, 0.0], [2.0]),
    ([0.1, 0.05], [1.0]),
])
def test_observed_order_refuses_insufficient_or_nondecreasing_refinement_data(errors, ratios):
    assert verify._observed_order(errors, ratios) is None


def test_observed_order_matches_exact_second_order_convergence():
    assert verify._observed_order([0.04, 0.01], [2.0]) == pytest.approx(2.0)


@pytest.mark.parametrize("last,order,ratio", [
    (0.1, None, 2.0), (0.1, 0.0, 2.0), (0.1, -1.0, 2.0),
    (0.1, 1.0, 1.0), (0.1, 1e-20, 2.0),
])
def test_richardson_error_refuses_unsupported_extrapolation(last, order, ratio):
    assert verify._richardson_error(last, order, ratio) is None


def test_richardson_error_is_exact_for_known_order_two():
    assert verify._richardson_error(0.03, 2.0, 2.0) == pytest.approx(0.01)


@pytest.mark.parametrize("tolerance", [0.0, -1.0, float("nan"), float("inf")])
def test_refinement_does_not_accept_invalid_tolerance(tolerance):
    with pytest.raises(ValueError, match="finite and positive"):
        study(model(ModelFamily.ODE), tolerance=tolerance)


def test_refinement_requires_two_or_more_observation_times():
    with pytest.raises(ValueError, match="points must be at least 2"):
        verify.numerical_refinement_study(
            model(ModelFamily.ODE), simulate_once=lambda *args, **kwargs: {},
            t_span=(0.0, 1.0), points=1,
        )


@pytest.mark.parametrize("run_count,points,work,level", [
    (1, 2, 1, "low"),
    (10, 500, 20, "medium"),
    (10, 5000, 50, "high"),
])
def test_approval_payload_reports_calculated_work_without_running_solver(
    run_count, points, work, level,
):
    result = verify._approval_payload(
        model(ModelFamily.PDE), study="mesh_refinement",
        runs=run_count, points=points, work_scale=work,
    )
    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["cost"]["level"] == level
    assert result["cost"]["requires_user_approval"] is True
    assert result["cost"]["estimated_work_units"] == run_count * points * work


def test_unapproved_pde_refinement_never_executes_hidden_computation():
    result = study(model(ModelFamily.PDE), approve_heavy=False)
    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["study"] == "mesh_refinement"


def test_unapproved_ode_refinement_never_executes_hidden_computation():
    result = study(model(ModelFamily.ODE), approve_heavy=False)
    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["study"] == "solver_tolerance_refinement"


@pytest.mark.parametrize("bad,pattern", [
    ([], "metadata.pde must be an object"),
    ({"grid_points": 4}, "grid_points must be at least 5"),
    ({"grid_points": 2049}, "too large to construct"),
    ({"grid_points": 5000}, "too large to construct"),
])
def test_pde_mesh_refinement_rejects_invalid_or_unrefinable_grid(bad, pattern):
    ir = model(ModelFamily.PDE)
    ir.metadata["pde"] = bad
    with pytest.raises(ValueError, match=pattern):
        study(ir, approve_heavy=False)


def test_failed_pde_solver_does_not_claim_mesh_convergence():
    bad = {"status": "FAIL", "cause": "numerical solver refused"}
    result = study(model(ModelFamily.PDE), lambda *args, **kwargs: bad)
    assert result["status"] == "FAIL"
    assert result["failed_result"] == bad
    assert result["failed_grid_points"] >= 5


@pytest.mark.parametrize("broken,pattern", [
    ({"status": "PASS", "states": {"u": [[1.0]]}}, "requires spatial coordinates"),
    ({"status": "PASS", "coordinates": {"x": [0.0, 1.0]}}, "requires state arrays"),
])
def test_pde_missing_observations_cannot_pass_refinement(broken, pattern):
    with pytest.raises(ValueError, match=pattern):
        study(model(ModelFamily.PDE), lambda *args, **kwargs: broken)


def test_pde_rejects_changed_state_identity_between_refinement_levels():
    count = 0
    def mismatch(ir, **kwargs):
        nonlocal count
        count += 1
        actual = pde_snapshot(ir)
        if count == 2:
            actual["states"] = {"different_u": actual["states"]["u"]}
        return actual

    with pytest.raises(ValueError, match="missing from refined PDE result"):
        study(model(ModelFamily.PDE), mismatch)


def test_pde_rejects_trajectory_missing_time_space_axes():
    def invalid_shape(ir, **kwargs):
        actual = pde_snapshot(ir)
        actual["states"]["u"] = actual["states"]["u"][-1]
        return actual

    with pytest.raises(ValueError, match="time-by-space matrices"):
        study(model(ModelFamily.PDE), invalid_shape)


def test_valid_constant_field_refinement_has_no_invented_error():
    result = study(model(ModelFamily.PDE), pde_snapshot)
    assert result["status"] == "PASS"
    assert result["converged"]
    assert len(result["comparisons"]) >= 1
    assert result["estimated_numerical_error"] == pytest.approx(0.0)


def test_failed_ode_solver_does_not_claim_tolerance_convergence():
    result = study(model(ModelFamily.ODE), lambda *args, **kwargs: {"status": "FAIL"})
    assert result["status"] == "FAIL"
    assert result["study"] == "solver_tolerance_refinement"
    assert result["failed_result"]["status"] == "FAIL"


def test_missing_ode_trajectory_cannot_be_substituted_with_zero_error():
    with pytest.raises(ValueError, match="requires state trajectories"):
        study(model(ModelFamily.ODE), lambda *args, **kwargs: {"status": "PASS"})


def test_refinement_of_unsupported_family_is_explicitly_not_applicable():
    result = study(model(ModelFamily.CAUSAL))
    assert result["status"] == "NOT_APPLICABLE"
    assert result["uncertainty_separation"]["numerical"] != 0.0


def test_default_runtime_scope_remains_finite_and_reproducible():
    assert math.isfinite(verify._relative_errors(np.array([1.0]), np.array([2.0]))[0])


def test_real_scipy_ode_tolerance_refinement_uses_actual_native_trajectories():
    from axiomize.general_engine import simulate_model

    result = verify.numerical_refinement_study(
        model(ModelFamily.ODE), simulate_once=simulate_model,
        t_span=(0.0, 1.0), points=20, seed=7,
        tolerance=1e-3, approve_heavy=True,
    )
    assert result["status"] == "PASS", result
    assert result["converged"] is True
    assert result["study"] == "solver_tolerance_refinement"
    assert len(result["comparisons"]) == 2
    assert result["estimated_numerical_error"] < 1e-3
    assert result["uncertainty_separation"]["numerical"] < 1e-3
    assert "parameter" in result["uncertainty_separation"]
