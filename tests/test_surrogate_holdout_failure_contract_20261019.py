"""Independent surrogate validation: real fit and fail-closed generation paths."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from axiomize import surrogate
from axiomize.model_ir import ModelIR


def _data(size=36):
    x = np.linspace(-1.0, 1.0, size)
    return {"x": x.tolist()}, {"y": (1 + 2 * x).tolist()}


def _source():
    return ModelIR.from_dict({
        "schema_version": "1.0", "domain": "physics", "name": "bounded-decay",
        "family": "ode",
        "variables": [{"name": "x", "initial": 1.0}],
        "parameters": [{"name": "k", "value": 0.5, "bounds": [0.0, 1.0]}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    })


def test_name_collisions_from_nonstring_data_keys_are_refused():
    x, y = _data(12)
    with pytest.raises(ValueError, match="names must be unique"):
        surrogate._validate_training_data({1: x["x"], "1": x["x"]}, y)
    with pytest.raises(ValueError, match="names must be unique"):
        surrogate._validate_training_data(x, {1: y["y"], "1": y["y"]})


def test_more_than_twelve_source_dimensions_are_not_implicitly_supported():
    y = {"y": list(range(9))}
    columns = {f"x{i}": [float(j + i) for j in range(9)] for i in range(13)}
    with pytest.raises(ValueError, match="at most 12 inputs"):
        surrogate._validate_training_data(columns, y)


def test_small_dataset_reserves_five_training_observations():
    x, y = _data(8)
    fitted = surrogate.fit_polynomial_surrogate(
        inputs=x, outputs=y, holdout_fraction=0.5, degree=1,
    )
    assert fitted["status"] == "PASS"
    assert fitted["surrogate"]["training_rows"] == 5
    assert fitted["surrogate"]["holdout_rows"] == 3
    assert fitted["surrogate"]["use_policy"]["may_replace_full_model"] is False


def test_singular_solver_fallback_reports_actual_holdout_error(monkeypatch):
    x, y = _data(36)

    def singular(*args, **kwargs):
        raise np.linalg.LinAlgError("singular matrix")

    monkeypatch.setattr(surrogate.np.linalg, "solve", singular)
    fitted = surrogate.fit_polynomial_surrogate(
        inputs=x, outputs=y, degree=1, seed=3,
    )
    assert fitted["status"] == "PASS"
    assert fitted["surrogate"]["validation"]["holdout_metrics"]["y"]["rmse"] < 1e-6


def test_missing_source_model_state_must_request_explicit_output_specs():
    model = SimpleNamespace(
        variables=[SimpleNamespace(name="x", role="output")],
    )
    with pytest.raises(ValueError, match="has no state outputs"):
        surrogate._output_specs(model, None)


def test_zero_successful_raw_model_runs_cannot_create_surrogate(monkeypatch):
    attempted = []

    def rejected(*args, **kwargs):
        attempted.append(kwargs["seed"])
        return {"status": "FAIL", "stage": "upstream-solver-refusal"}

    monkeypatch.setattr(surrogate, "simulate_model", rejected)
    out = surrogate.generate_and_fit_surrogate(
        _source(), parameter_ranges={"k": [0.1, 0.8]},
        samples=8, points=12, approve_heavy=True,
    )
    assert out["status"] == "FAIL"
    assert out["stage"] == "training_data_generation"
    assert out["successful_runs"] == 0
    assert out["failed_runs"] == 8
    assert len(attempted) == 8
    assert {row["stage"] for row in out["failures"]} == {"upstream-solver-refusal"}
    assert "surrogate" not in out


def test_simulation_with_malformed_output_is_never_counted_as_success(monkeypatch):
    monkeypatch.setattr(surrogate, "simulate_model", lambda *args, **kwargs: {
        "status": "PASS", "states": {},
    })
    out = surrogate.generate_and_fit_surrogate(
        _source(), parameter_ranges={"k": [0.1, 0.8]},
        samples=8, points=12, approve_heavy=True,
    )
    assert out["status"] == "FAIL"
    assert out["successful_runs"] == 0
    assert out["failed_runs"] == 8
    assert all(row["status"] == "OUTPUT_EXTRACTION_FAIL" for row in out["failures"])
    assert all("lacks state" in row["detail"] for row in out["failures"])


def test_partial_failures_are_recorded_and_never_backfilled(monkeypatch):
    attempted = []

    def intermittent(*args, **kwargs):
        attempted.append(kwargs["seed"])
        if len(attempted) % 2:
            return {"status": "FAIL", "stage": "scientific-constraint"}
        return {"status": "PASS", "states": {"x": [1.0, 0.5]}}

    monkeypatch.setattr(surrogate, "simulate_model", intermittent)
    out = surrogate.generate_and_fit_surrogate(
        _source(), parameter_ranges={"k": [0.1, 0.8]},
        samples=12, points=12, approve_heavy=True,
    )
    assert out["status"] == "FAIL"
    assert out["successful_runs"] == 6
    assert out["failed_runs"] == 6
    assert out["minimum_successful_runs"] == 8


def test_untouched_holdout_and_reproducibility_still_apply_after_fallback():
    x, y = _data()
    left = surrogate.fit_polynomial_surrogate(inputs=x, outputs=y, degree=1, seed=7)
    right = surrogate.fit_polynomial_surrogate(inputs=x, outputs=y, degree=1, seed=7)
    assert left == right
    assert left["validation_status"] == "PASS"
    assert left["surrogate"]["validation"]["method"] == "seeded_untouched_holdout"
