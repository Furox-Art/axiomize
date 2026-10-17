"""Approval gates and exact validation status at every Model IR service boundary."""

from __future__ import annotations

import copy

import pytest

from axiomize.application import general_services as s


def model_ir():
    return {
        "schema_version": "1.0",
        "name": "measured_decay",
        "family": "ode",
        "domain": "physics",
        "variables": [{"name": "x", "initial": 1.0, "unit": "dimensionless"}],
        "parameters": [{"name": "k", "value": 0.3, "bounds": [0.0, 1.0]}],
        "equations": [{"target": "x", "kind": "derivative", "expression": "-k*x"}],
    }


def legacy_model():
    return {
        "schema_version": "0.9",
        "name": "legacy",
        "domain": "physics",
        "model_family": "ode",
        "states": {"x": 1.0},
        "rhs": {"x": "-x"},
    }


@pytest.mark.parametrize(
    "service",
    [
        s.model_plan_service,
        s.model_validate_service,
        s.model_simulate_service,
        s.model_fit_service,
        s.model_repair_service,
        s.model_export_service,
        s.model_stability_service,
        s.model_validity_service,
        s.experiment_design_service,
    ],
)
def test_version_migration_requires_explicit_consent_across_all_interfaces(service):
    out = service({"model_ir": legacy_model()})
    assert out["status"] == "APPROVAL_REQUIRED"
    assert out["action"] == "ir_migration"
    assert out["migration"]["from"] == "0.9"
    assert out["migration"]["to"] == "1.0"


@pytest.mark.parametrize(
    ("span", "pattern"),
    [
        ([], "t_span"),
        ("0,1", "t_span"),
        ([0.0], "t_span"),
        ([2.0, 1.0], "strictly increasing"),
        ([0.0, float("nan")], "finite"),
        ([0.0, "not a number"], "numeric"),
    ],
)
def test_model_service_requires_finite_time_domain(span, pattern):
    with pytest.raises(ValueError, match=pattern):
        s._span({"t_span": span})


def test_model_plan_never_invents_explicit_equations_from_vague_idea():
    out = s.model_plan_service({"idea": "test a growth model", "signals": ["time series"]})
    assert out["status"] == "NEEDS_MODEL_IR"
    assert out["candidate_count"] == len(out["candidate_families"])
    assert "next_contract" in out
    assert "model_ir" not in out


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "either idea or model_ir"),
        ({"idea": " " * 3}, "either idea or model_ir"),
        ({"idea": "x" * 200001}, "hard text limit"),
        ({"idea": "x", "signals": "invalid"}, "signals must be"),
        ({"idea": "x", "signals": [1] * 10001}, "signals must be"),
    ],
)
def test_model_planning_does_not_infer_hidden_scientific_inputs(payload, message):
    with pytest.raises(ValueError, match=message):
        s.model_plan_service(payload)


def test_planner_with_explicit_model_returns_provenance_and_execution_plan():
    out = s.model_plan_service({"model_ir": model_ir(), "points": 8, "action": "fit"})
    assert out["status"] == "PASS"
    assert out["model_ir"]["family"] == "ode"
    assert "plan" in out
    assert "identifiability_check" in out["plan"]["stages"]
    assert out["plan"]["model"] == "measured_decay"


@pytest.mark.parametrize(
    "service",
    [
        s.model_simulate_service,
        s.model_fit_service,
    ],
)
def test_invalid_dimensional_model_never_enters_native_executor(service, monkeypatch):
    invalid = copy.deepcopy(model_ir())
    invalid["equations"][0]["expression"] = "-k*x"
    invalid["parameters"][0]["unit"] = "meter"
    result = service({"model_ir": invalid})
    assert result["status"] == "FAIL"
    assert result["stage"] == "pre_validation"


def test_model_simulate_provenance_does_not_suppress_failed_native_validation(monkeypatch):
    monkeypatch.setattr(
        s,
        "simulate_model",
        lambda *a, **kw: {
            "status": "PASS",
            "validation": {"status": "FAIL", "checks": [{"name": "constraint", "status": "FAIL"}]},
        },
    )
    out = s.model_simulate_service({"model_ir": model_ir(), "points": 10})
    assert out["status"] == "FAIL"
    assert out["validation"]["status"] == "FAIL"
    assert "provenance" in out


def test_model_fit_receives_raw_series_and_retains_fitted_covariance_evidence(monkeypatch):
    captured = []

    def stub(model, *, time, observations, approve_heavy):
        captured.append((time, observations, approve_heavy))
        return {"status": "PASS", "covariance": [[0.04]], "residual_diagnostics": {"x": {"std": 0.2}}}

    monkeypatch.setattr(s, "fit_ode_model", stub)
    out = s.model_fit_service(
        {
            "model_ir": model_ir(),
            "time": [0.0, 1.0, 2.0],
            "observations": {"x": [1.0, 0.9, 0.7]},
            "approve_heavy": True,
        }
    )
    assert out["status"] == "PASS"
    assert captured == [([0.0, 1.0, 2.0], {"x": [1.0, 0.9, 0.7]}, True)]
    assert "uncertainty_components" in out
    assert out["validation"]["status"] != "FAIL"


@pytest.mark.parametrize(
    ("input_times", "obs", "pattern"),
    [
        ([0.0, 0.0], {"x": [1.0, 2.0]}, "strictly increasing"),
        ([0.0, float("nan")], {"x": [1.0, 2.0]}, "finite"),
        ([0.0, 1.0], {"x": [1.0]}, "length"),
        ([0.0, 1.0], {"x": [1.0, float("nan")]}, "finite"),
        ([0.0, 1.0], {}, "non-empty observations"),
        ([0.0, 1.0], [], "non-empty observations"),
    ],
)
def test_invalid_fit_observations_do_not_reach_solver(input_times, obs, pattern):
    with pytest.raises(ValueError, match=pattern):
        s.model_fit_service({"model_ir": model_ir(), "time": input_times, "observations": obs})


@pytest.mark.parametrize(
    ("function", "payload", "pattern"),
    [
        (s.model_stability_service, {"state": []}, "state object"),
        (s.model_stability_service, {"state": {"x": float("nan")}}, "finite"),
        (s.model_discovery_service, {"time": [0.0, 1.0, 2.0], "state": [1.0, 2.0, 3.0, 4.0]}, "lengths must match"),
        (
            s.model_discovery_service,
            {"time": [0.0, 1.0, 2.0], "state": [1.0, 2.0, 3.0], "threshold": -0.1},
            "non-negative",
        ),
        (s.experiment_design_service, {"candidate_times": [0.1], "horizon": 0.0, "parameter": "k"}, "positive"),
        (
            s.experiment_design_service,
            {"candidate_times": [0.1], "horizon": 1.0, "parameter": "k", "delta_fraction": 0.0},
            "in \\(0, 1\\]",
        ),
    ],
)
def test_invalid_diagnostics_input_is_rejected_before_compute(function, payload, pattern):
    with pytest.raises(ValueError, match=pattern):
        function({"model_ir": model_ir(), **payload})


@pytest.mark.parametrize(
    ("function", "name", "stub_return"),
    [
        (s.model_export_service, "export_model", {"status": "PASS", "format": "json"}),
        (s.model_repair_service, "repair_model", {"status": "APPROVAL_REQUIRED"}),
        (s.model_stability_service, "local_stability", {"classification": "stable"}),
        (s.model_validity_service, "validity_scan", {"status": "PASS", "evaluations": []}),
        (s.experiment_design_service, "rank_experiment_times", {"status": "APPROVAL_REQUIRED"}),
    ],
)
def test_approved_model_routes_reach_exact_backend(function, name, stub_return, monkeypatch):
    seen = []

    def stub(*a, **kw):
        seen.append((a, kw))
        return stub_return

    monkeypatch.setattr(s, name, stub)
    data = {
        "model_ir": model_ir(),
        "state": {"x": 0.8},
        "parameter": "k",
        "values": [0.1, 0.2],
        "candidate_times": [0.2, 0.4],
        "horizon": 1.0,
        "format": "json",
        "approve_repair": False,
    }
    assert function(data) == stub_return
    assert len(seen) == 1
