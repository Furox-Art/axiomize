"""Scientific surrogate training provenance and fail-closed internal guards."""
from __future__ import annotations

import numpy as np
import pytest

from axiomize import surrogate
from axiomize.model_ir import ModelIR


def model(*, bounded=True):
    parameter = {"name": "k", "value": 0.5}
    if bounded:
        parameter["bounds"] = [0.0, 1.0]
    return ModelIR.from_dict({
        "schema_version": "1.0", "domain": "physics", "name": "real-decay",
        "family": "ode",
        "variables": [{"name": "x", "initial": 1.0}],
        "parameters": [parameter],
        "equations": [{"target": "x", "kind": "derivative", "expression": "-k*x"}],
    })


def test_fail_closed_if_internal_validated_training_shape_is_corrupt(monkeypatch):
    # Fault injection tests the internal defensive bound, not valid raw input.
    monkeypatch.setattr(
        surrogate, "_validate_training_data",
        lambda *_: (
            ["x"], ["y"], np.ones((6, 1)), np.ones((6, 1)),
        ),
    )
    with pytest.raises(ValueError, match="not enough observations"):
        surrogate.fit_polynomial_surrogate(
            inputs={"x": list(range(8))},
            outputs={"y": list(range(8))},
            degree=1, holdout_fraction=0.5,
        )


def test_source_without_declared_bounds_can_use_explicit_finite_range():
    ranges = surrogate._validate_parameter_ranges(
        model(bounded=False), {"k": [0.2, 0.8]},
    )
    assert ranges == {"k": (0.2, 0.8)}


def test_explicit_output_spec_records_source_and_metric():
    specs = surrogate._output_specs(
        model(), [{"state": "x", "metric": "integral", "name": "integrated_value"}],
    )
    assert specs == [{
        "state": "x", "metric": "integral", "name": "integrated_value",
    }]
    assert surrogate._output_specs(model(), None)[0]["state"] == "x"


def test_invalid_explicit_output_specs_do_not_invent_training_labels():
    for raw, expected in (
        ({"state": "x"}, "non-empty array"),
        ([{"state": "unknown"}], "unknown state"),
        ([{"state": "x", "metric": "invented"}], "unsupported output metric"),
        ([{"state": "x", "name": "dup"}, {"state": "x", "name": "dup"}], "duplicate"),
    ):
        with pytest.raises(ValueError, match=expected):
            surrogate._output_specs(model(), raw)


def test_complete_real_ode_training_retains_model_provenance():
    result = surrogate.generate_and_fit_surrogate(
        model(), parameter_ranges={"k": [0.2, 0.8]},
        samples=12, points=30, degree=3, seed=17,
        approve_heavy=True,
    )
    assert result["status"] == "PASS"
    assert result["sampling"]["requested_runs"] == 12
    assert result["sampling"]["successful_runs"] == 12
    assert result["sampling"]["failed_runs"] == 0
    assert result["source_model"]["name"] == "real-decay"
    assert result["source_model"]["family"] == "ode"
    assert result["surrogate"]["sampling"] == result["sampling"]
    assert result["surrogate"]["provenance"] == result["provenance"]
    assert len(result["surrogate"]["dataset_sha256"]) == 64
    assert result["surrogate"]["use_policy"]["may_replace_full_model"] is False


def test_partial_solver_refusals_are_included_in_successful_surrogate_provenance(monkeypatch):
    calls = []

    def measured_with_gaps(*args, **kwargs):
        calls.append(kwargs["seed"])
        if len(calls) in (2, 7):
            return {"status": "FAIL", "stage": "solver-refused"}
        k = kwargs["parameter_overrides"]["k"]
        return {"status": "PASS", "states": {"x": [1.0, float(np.exp(-k))]}}

    monkeypatch.setattr(surrogate, "simulate_model", measured_with_gaps)
    report = surrogate.generate_and_fit_surrogate(
        model(), parameter_ranges={"k": [0.2, 0.8]},
        samples=12, points=12, degree=2, seed=17,
        approve_heavy=True,
    )
    assert report["status"] == "PASS"
    assert report["sampling"]["successful_runs"] == 10
    assert report["sampling"]["failed_runs"] == 2
    assert report["sampling"]["success_fraction"] == pytest.approx(10 / 12)
    assert [row["sample"] for row in report["sampling"]["failures"]] == [1, 6]
    assert {row["stage"] for row in report["sampling"]["failures"]} == {"solver-refused"}


def test_missing_output_for_successfully_labeled_model_is_not_training_data(monkeypatch):
    # Status PASS is insufficient: direct state values must be present.
    calls = []

    def source(*args, **kwargs):
        calls.append(kwargs["seed"])
        return {"status": "PASS", "states": {"not_x": [1.0, 0.5]}}

    monkeypatch.setattr(surrogate, "simulate_model", source)
    result = surrogate.generate_and_fit_surrogate(
        model(), parameter_ranges={"k": [0.2, 0.8]},
        samples=8, points=10, approve_heavy=True,
    )
    assert result["stage"] == "training_data_generation"
    assert result["successful_runs"] == 0
    assert result["failed_runs"] == len(calls) == 8
