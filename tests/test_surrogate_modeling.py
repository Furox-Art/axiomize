from __future__ import annotations

import math

import numpy as np

from axiomize.application.surrogate_services import model_surrogate_service
from axiomize.model_ir import ModelIR
from axiomize.surrogate import evaluate_surrogate, fit_polynomial_surrogate


def _quadratic_data(n: int = 80) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    rng = np.random.default_rng(17)
    a = rng.uniform(-2.0, 2.0, size=n)
    b = rng.uniform(-1.5, 1.5, size=n)
    y = 1.0 + 2.0 * a - 0.5 * b + 0.3 * a * b + 0.2 * a**2
    return {"a": a.tolist(), "b": b.tolist()}, {"y": y.tolist()}


def _decay_model() -> ModelIR:
    return ModelIR.from_dict({
        "schema_version": "1.0",
        "name": "decay-surrogate-source",
        "domain": "physics",
        "family": "ode",
        "independent_variable": "t",
        "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
        "parameters": [{"name": "k", "unit": "1/day", "value": 0.3, "bounds": [0.05, 0.8]}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
        "constraints": [{"name": "nonnegative", "kind": "nonnegative", "variables": ["x"], "severity": "error"}],
    })


def test_polynomial_surrogate_passes_untouched_holdout_for_exact_response() -> None:
    inputs, outputs = _quadratic_data()
    out = fit_polynomial_surrogate(
        inputs=inputs,
        outputs=outputs,
        degree=2,
        seed=11,
        minimum_r2=0.999999,
        maximum_nrmse=1e-6,
    )
    assert out["status"] == "PASS"
    assert out["validation_status"] == "PASS"
    assert out["qualified_for_acceleration"] is True
    artifact = out["surrogate"]
    assert artifact["validation"]["validated"] is True
    assert artifact["use_policy"]["may_replace_full_model"] is False
    assert artifact["dataset_sha256"]


def test_surrogate_prediction_is_accurate_inside_training_domain() -> None:
    inputs, outputs = _quadratic_data()
    fitted = fit_polynomial_surrogate(inputs=inputs, outputs=outputs, degree=2, seed=4)
    artifact = fitted["surrogate"]
    a, b = 0.4, -0.2
    expected = 1.0 + 2.0 * a - 0.5 * b + 0.3 * a * b + 0.2 * a**2
    out = evaluate_surrogate(artifact, inputs={"a": a, "b": b})
    assert out["status"] == "PASS"
    assert abs(out["predictions"]["y"] - expected) < 1e-8


def test_surrogate_blocks_extrapolation_by_default() -> None:
    inputs, outputs = _quadratic_data()
    artifact = fit_polynomial_surrogate(inputs=inputs, outputs=outputs, degree=2)["surrogate"]
    out = evaluate_surrogate(artifact, inputs={"a": 100.0, "b": 0.0})
    assert out["status"] == "OUT_OF_DOMAIN"
    assert "predictions" not in out
    assert out["violations"][0]["input"] == "a"


def test_failed_holdout_surrogate_is_not_usable_by_default() -> None:
    x = np.linspace(-math.pi, math.pi, 60)
    fitted = fit_polynomial_surrogate(
        inputs={"x": x.tolist()},
        outputs={"y": np.sin(5.0 * x).tolist()},
        degree=1,
        seed=3,
        minimum_r2=0.99,
        maximum_nrmse=0.01,
    )
    assert fitted["status"] == "PASS"
    assert fitted["validation_status"] == "FAIL"
    assert fitted["qualified_for_acceleration"] is False
    evaluated = evaluate_surrogate(fitted["surrogate"], inputs={"x": 0.0})
    assert evaluated["status"] == "SURROGATE_REJECTED"


def test_full_model_training_generation_requires_explicit_approval() -> None:
    model = _decay_model()
    out = model_surrogate_service({
        "mode": "generate",
        "model_ir": model.to_dict(),
        "parameter_ranges": {"k": [0.1, 0.6]},
        "samples": 24,
        "points": 30,
        "t_span": [0.0, 2.0],
    })
    assert out["status"] == "APPROVAL_REQUIRED"
    assert out["action"] == "surrogate_training_data_generation"
    assert out["cost"]["requires_user_approval"] is True
    assert out["cost"]["full_model_runs"] == 24


def test_approved_full_model_generation_quantifies_surrogate_error() -> None:
    model = _decay_model()
    out = model_surrogate_service({
        "mode": "generate",
        "model_ir": model.to_dict(),
        "parameter_ranges": {"k": [0.1, 0.6]},
        "output_specs": [{"name": "x_final", "state": "x", "metric": "final"}],
        "samples": 40,
        "points": 35,
        "degree": 3,
        "t_span": [0.0, 2.0],
        "seed": 7,
        "minimum_r2": 0.995,
        "maximum_nrmse": 0.03,
        "approve_heavy": True,
    })
    assert out["status"] == "PASS"
    assert out["validation_status"] == "PASS"
    assert out["sampling"]["requested_runs"] == 40
    assert out["sampling"]["successful_runs"] == 40
    assert out["surrogate"]["source_model"]["name"] == model.name
    holdout = out["surrogate"]["validation"]["holdout_metrics"]["x_final"]
    assert holdout["r2"] >= 0.995
    assert holdout["nrmse"] <= 0.03
    assert out["provenance"]["data_hash"] == out["surrogate"]["dataset_sha256"]


def test_fit_from_supplied_data_needs_no_full_model_approval() -> None:
    inputs, outputs = _quadratic_data()
    out = model_surrogate_service({
        "mode": "fit",
        "training_data": {"inputs": inputs, "outputs": outputs},
        "degree": 2,
    })
    assert out["status"] == "PASS"
    assert out["mode"] == "fit_from_supplied_data"
    assert out["qualified_for_acceleration"] is True
