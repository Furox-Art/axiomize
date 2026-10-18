"""Second-generation numerical checks separate replay error from stochastic uncertainty."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize import numerical_verification_v2 as verify
from axiomize.model_ir import ModelFamily, ModelIR, VariableSpec


def observed_model(family=ModelFamily.STOCHASTIC):
    return ModelIR(
        name="direct numerical comparison",
        domain="physics",
        family=family,
        variables=[VariableSpec("x", initial=1.0)],
        parameters=[],
        equations=[],
    )


def call(**kw):
    return dict(
        t_span=(0.0, 1.0),
        points=10,
        parameter_overrides=None,
        seed=11,
        tolerance=1e-4,
        approve_heavy=True,
        **kw,
    )


def test_numeric_leaf_extraction_ignores_boolean_null_seed_and_unavailable_values():
    values = {
        "time": [0.0, 1.0],
        "seed": 12,
        "ok": True,
        "nothing": None,
        "observed": [1.0, 2.0],
        "quality": {"error": 0.5, "runtime_s": 20.0},
        "unavailable": float("nan"),
    }
    leaves = verify._numeric_leaves(values)
    assert leaves["observed"] == pytest.approx(1.5)
    assert leaves["observed.norm"] == pytest.approx(math.sqrt(5))
    assert leaves["quality.error"] == 0.5
    assert "time" not in leaves
    assert "seed" not in leaves
    assert "ok" not in leaves
    assert "unavailable" not in leaves
    assert "quality.runtime_s" not in leaves


def test_numeric_leaf_extraction_ignores_too_many_samples_without_allocating_array():
    assert verify._numeric_leaves({"large": list(range(10001))}) == {}


def test_numeric_leaf_extraction_has_no_invented_summary_for_empty_array():
    assert verify._numeric_leaves({"empty": []}) == {}


def test_numeric_leaf_extraction_rejects_nonfinite_batch_without_silent_record_drops():
    assert verify._numeric_leaves({"measurements": [0.0, float("inf")]}) == {}


@pytest.mark.parametrize(
    "contents",
    [
        {"states": "invalid"},
        {"states": {}},
        {"other": 3},
    ],
)
def test_no_recorded_state_is_an_empty_observation_not_a_fake_vector(contents):
    assert verify._terminal_states(contents).size == 0


def test_terminal_state_vector_reads_last_observation_for_each_real_state():
    result = {"states": {"beta": [[1.0, 2.0], [3.0, 4.0]], "alpha": [4.0, 5.0, 6.0]}}
    np.testing.assert_array_equal(verify._terminal_states(result), [6.0, 3.0, 4.0])


def test_empty_state_is_ignored_without_a_fake_zero_component():
    result = {"states": {"a": [], "b": [2.0, 3.0]}}
    np.testing.assert_array_equal(verify._terminal_states(result), [3.0])


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ([1.0], [1.0, 2.0]),
        ([float("nan")], [0.0]),
        ([1.0], [float("inf")]),
    ],
)
def test_relative_error_refuses_mismatched_or_nonfinite_direct_observations(a, b):
    with pytest.raises(ValueError, match="incompatible/non-finite"):
        verify._relative(np.asarray(a), np.asarray(b))


def test_true_relative_error_on_simple_arrays_has_exact_analytic_value():
    assert verify._relative(np.array([1.0, 2.0]), np.array([1.0, 4.0])) == pytest.approx(2 / math.sqrt(17))


def test_unapproved_replay_returns_explicit_cost_gate_and_does_not_simulate():
    def forbidden(*_args, **_kw):
        pytest.fail("simulation must not run without authorization")

    result = verify.numerical_refinement_study_v2(
        observed_model(),
        simulate_once=forbidden,
        t_span=(0.0, 1.0),
        points=12,
    )
    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["cost"]["requires_user_approval"] is True


def test_actual_replay_uses_identical_seed_and_preserves_stochastic_uncertainty_separately():
    calls = []

    def observed(_model, **kw):
        calls.append(kw)
        return {"status": "PASS", "measure": {"value": 7.0}}

    result = verify.numerical_refinement_study_v2(
        observed_model(),
        simulate_once=observed,
        t_span=(0.0, 1.0),
        points=14,
        approve_heavy=True,
    )
    assert result["status"] == "PASS"
    assert result["estimated_numerical_error"] == 0.0
    assert len(calls) == 2
    assert calls[0]["seed"] == calls[1]["seed"] == 0
    assert result["uncertainty_separation"]["aleatoric"].startswith("not estimated")


def test_actual_nonreproducibility_under_identical_seed_must_fail():
    index = [0]

    def nondeterministic(_model, **_kw):
        index[0] += 1
        return {"status": "PASS", "observed": float(index[0])}

    result = verify.numerical_refinement_study_v2(
        observed_model(),
        simulate_once=nondeterministic,
        t_span=(0.0, 1.0),
        points=12,
        approve_heavy=True,
        tolerance=0.01,
    )
    assert result["status"] == "FAIL"
    assert result["estimated_numerical_error"] > 0.0


def test_failed_replay_is_reported_as_failure_not_suppressed():
    with pytest.raises(RuntimeError, match="verification replay failed"):
        verify.numerical_refinement_study_v2(
            observed_model(),
            simulate_once=lambda *_a, **_kw: {"status": "FAIL"},
            t_span=(0.0, 1.0),
            approve_heavy=True,
        )


def test_unapproved_trajectory_refinement_never_spawns_its_heavy_executor():
    def forbidden(*_args, **_kw):
        pytest.fail("heavy resolution run requires explicit approval")

    out = verify.numerical_refinement_study_v2(
        observed_model(ModelFamily.CONTROL),
        simulate_once=forbidden,
        t_span=(0.0, 1.0),
        points=12,
    )
    assert out["status"] == "APPROVAL_REQUIRED"
    assert out["study"] == "output_resolution_refinement"


def test_trajectory_refinement_tracks_actual_terminal_state_difference():
    called = []

    def observed(_model, **kw):
        called.append(kw["points"])
        return {"status": "PASS", "states": {"x": [1.0, float(kw["points"])]}}

    out = verify.numerical_refinement_study_v2(
        observed_model(ModelFamily.CONTROL),
        simulate_once=observed,
        t_span=(0.0, 1.0),
        points=10,
        approve_heavy=True,
        tolerance=0.001,
    )
    assert called == [10, 19]
    assert out["status"] == "FAIL"
    assert out["error_metric"] == "terminal-state relative L2 difference"
    assert out["estimated_numerical_error"] == pytest.approx(9 / 19)


def test_trajectory_without_states_uses_only_recorded_numeric_values():
    called = []

    def observed(_model, **kw):
        called.append(kw["points"])
        return {"status": "PASS", "actual_measurement": 10.0}

    out = verify.numerical_refinement_study_v2(
        observed_model(ModelFamily.NETWORK),
        simulate_once=observed,
        t_span=(0.0, 1.0),
        points=8,
        approve_heavy=True,
    )
    assert called == [8, 15]
    assert out["estimated_numerical_error"] == 0.0
    assert out["error_metric"] == "numeric-summary relative difference"


def test_maximum_output_resolution_falls_back_to_same_seed_replay():
    called = []

    def observed(_model, **kw):
        called.append(kw["points"])
        return {"status": "PASS", "actual_measurement": 10.0}

    out = verify.numerical_refinement_study_v2(
        observed_model(ModelFamily.NETWORK),
        simulate_once=observed,
        t_span=(0.0, 1.0),
        points=200000,
        approve_heavy=True,
    )
    assert out["study"] == "same_seed_reproducibility"
    assert called == [200000, 200000]


def test_optimizer_family_uses_replay_not_fabricated_mesh_grid():
    out = verify.numerical_refinement_study_v2(
        observed_model(ModelFamily.OPTIMIZATION),
        simulate_once=lambda *_a, **_kw: {"status": "PASS", "objective": 2.0},
        t_span=(0.0, 1.0),
        approve_heavy=True,
    )
    assert out["study"] == "same_seed_reproducibility"
    assert out["status"] == "PASS"


@pytest.mark.parametrize("tolerance", [0.0, -1.0, float("nan"), float("inf")])
def test_replay_tolerance_must_be_finite_and_positive(tolerance):
    with pytest.raises(ValueError, match="tolerance must be finite"):
        verify.numerical_refinement_study_v2(
            observed_model(),
            simulate_once=lambda *_a, **_kw: {"status": "PASS"},
            t_span=(0.0, 1.0),
            tolerance=tolerance,
        )


def test_numerical_refinement_requires_at_least_two_output_points():
    with pytest.raises(ValueError, match="at least 2"):
        verify.numerical_refinement_study_v2(
            observed_model(),
            simulate_once=lambda *_a, **_kw: {"status": "PASS"},
            t_span=(0.0, 1.0),
            points=1,
        )
