"""Exercise actual general Model IR service contracts with typed invalid inputs.

No simulated PASS from mocked scientific kernels or implicit user approval.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from axiomize.application import general_services as svc
from axiomize.model_ir import ModelIR


def ode():
    return ModelIR.from_dict({
        "schema_version": "1.0", "domain": "physics", "name": "exact-decay",
        "family": "ode", "variables": [{"name": "x", "initial": 1.0}],
        "parameters": [{"name": "k", "value": 0.5, "fit": True}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    }).to_dict()


@pytest.mark.parametrize("raw,error", [
    (None, "numeric"), ("garbled", "numeric"), (float("nan"), "finite"),
    (float("inf"), "finite"), (-float("inf"), "finite"),
])
def test_service_scalar_inputs_do_not_create_finite_measurements(raw, error):
    with pytest.raises(ValueError, match=error):
        svc._finite(raw, name="observation")


@pytest.mark.parametrize("span,fragment", [
    ([], "contain"), ([0], "contain"), ([0, 1, 2], "contain"),
    ("1,2", "contain"), ([2, 1], "increasing"),
    ([1, 1], "increasing"), ([0, float("nan")], "finite"),
    (["error", 2], "numeric"),
])
def test_model_time_span_is_explicitly_bounded(span, fragment):
    with pytest.raises(ValueError, match=fragment):
        svc._span({"t_span": span})


def test_unset_time_span_is_explicit_unit_interval():
    assert svc._span({}) == (0.0, 1.0)
    assert svc._span({"t_span": [1, 3]}) == (1.0, 3.0)


@pytest.mark.parametrize("bad", [0, 1, -1, 1.25, True, "invalid", 10**9])
def test_model_point_count_refuses_nonintegral_unbounded_requests(bad):
    with pytest.raises(ValueError):
        svc._points({"points": bad})


@pytest.mark.parametrize("invalid", [{}, {"model": []}, {"model_ir": 1}, {"model": "x"}])
def test_model_loading_requires_structured_model_ir(invalid):
    with pytest.raises(ValueError, match="model_ir"):
        svc._raw_model(invalid)


def test_real_model_plan_executes_native_model_ir_planning():
    result = svc.model_plan_service({"model_ir": ode(), "points": 12, "samples": 1})
    assert result["status"] == "PASS"
    assert result["model_ir"]["family"] == "ode"
    assert result["plan"] and result["provenance"]
    assert result["nondimensionalization"]


def test_idea_only_plan_never_invents_model_equations():
    result = svc.model_plan_service({"idea": "chemical diffusion", "signals": {"stochastic": True, "unused": False}})
    assert result["status"] == "NEEDS_MODEL_IR"
    assert result["candidate_count"] > 0
    assert "equations" in result["next_contract"]["required"]


@pytest.mark.parametrize("bad, fragment", [
    ({"idea": ""}, "requires either idea"),
    ({"idea": "x" * 200001}, "hard text limit"),
    ({"idea": "reaction", "signals": "not-array"}, "signals"),
    ({"idea": "reaction", "signals": [0] * 10001}, "signals"),
    ({"idea": "reaction", "signals": {str(x): True for x in range(10001)}}, "hard limit"),
])
def test_planning_refuses_missing_or_unbounded_requests(bad, fragment):
    with pytest.raises(ValueError, match=fragment):
        svc.model_plan_service(bad)


def test_native_validation_is_not_a_mock_pass():
    result = svc.model_validate_service({"model_ir": ode()})
    assert result["status"] == "PASS", result
    assert result["validation"]["status"] == "PASS"
    assert result["provenance"]


def test_real_simulation_exposes_actual_decay_and_provenance():
    result = svc.model_simulate_service({
        "model_ir": ode(), "t_span": [0, 2], "points": 21, "seed": 19,
    })
    assert result["status"] == "PASS", result
    assert result["states"]["x"][-1] == pytest.approx(np.exp(-1), abs=1e-4)
    assert result["provenance"]


def test_fit_requires_conserved_time_and_observation_rows():
    base = {"model_ir": ode(), "time": [0, 1, 2], "observations": {"x": [1, 0.6, 0.3]}}
    for values, match in [
        ({"observations": None}, "observations object"),
        ({"observations": {}}, "observations object"),
        ({"observations": {"x": [1, 2]}}, "length must equal"),
        ({"observations": {"x": [1, float("nan"), 3]}}, "only finite"),
        ({"time": [0, 2, 1]}, "strictly increasing"),
        ({"time": [0, 1, float("inf")]}, "finite"),
    ]:
        with pytest.raises(ValueError, match=match):
            svc.model_fit_service({**base, **values})


def test_bounded_direct_fit_produces_reproducible_likelihood_evidence():
    request = {
        "model_ir": ode(), "time": [0, 1, 2],
        "observations": {"x": [1, 0.6, 0.3]},
    }
    actual = svc.model_fit_service(request)
    assert actual["status"] == "PASS", actual
    assert actual["validation"]["status"] == "PASS"
    assert actual["provenance"]


def test_native_model_comparison_does_not_relabel_worse_fit_as_winner():
    actual = svc.model_compare_service({
        "fits": {
            "simple": {"selection_scores": {"bic": 2.0, "aic": 3.0, "sse": 1.0}},
            "complex": {"selection_scores": {"bic": 6.0, "aic": 1.0, "sse": 0.8}},
        }, "criterion": "bic",
    })
    assert actual["winner"] == "simple"


@pytest.mark.parametrize("fits", [None, {}, [], {"x": 1}])
def test_missing_fit_evidence_is_not_silently_ranked(fits):
    with pytest.raises((ValueError, TypeError)):
        svc.model_compare_service({"fits": fits})


def test_model_repair_does_not_mutate_without_approval():
    actual = svc.model_repair_service({"model_ir": ode()})
    assert actual["status"] in {"PASS", "APPROVAL_REQUIRED", "NO_REPAIR_NEEDED"}
    assert not actual.get("applied", False)


def test_json_export_contains_exact_provided_equations():
    actual = svc.model_export_service({"model_ir": ode(), "format": "json"})
    assert actual["format"] == "json"
    parsed = json.loads(actual["content"])
    assert parsed["equations"][0]["expression"] == "-k*x"


@pytest.mark.parametrize("state, fragment", [
    (None, "state object"), ("x", "state object"),
    ({"x": float("nan")}, "finite"), ({"x": "invalid"}, "numeric"),
])
def test_local_stability_rejects_ambiguous_state(state, fragment):
    with pytest.raises(ValueError, match=fragment):
        svc.model_stability_service({"model_ir": ode(), "state": state})


def test_native_equilibrium_stability_is_a_real_jacobian_calculation():
    actual = svc.model_stability_service({"model_ir": ode(), "state": {"x": 0.0}})
    assert actual["classification"] == "stable"
    assert actual["jacobian"][0][0] == pytest.approx(-0.5)


def test_unapproved_validity_scan_never_runs_heavy_simulations():
    actual = svc.model_validity_service({
        "model_ir": ode(), "parameter": "k", "values": [0.1, 0.5], "points": 15,
    })
    assert actual["status"] == "APPROVAL_REQUIRED"


@pytest.mark.parametrize("raw,match", [
    ({"time": [0, 1, 2], "state": [1, 2]}, "state length"),
    ({"time": [0, 1, 2], "state": [1, 2, 3], "degree": 0}, "degree"),
    ({"time": [0, 1, 2], "state": [1, 2, 3], "threshold": -1}, "non-negative"),
    ({"time": [0, 1, 2], "state": [1, 2, 3], "threshold": float("nan")}, "finite"),
])
def test_sparse_model_discovery_validates_actual_raw_observations(raw, match):
    with pytest.raises(ValueError, match=match):
        svc.model_discovery_service(raw)


def test_unapproved_sparse_discovery_is_correctly_approval_gated():
    t = np.linspace(0, 1, 5)
    x = np.exp(-t)
    result = svc.model_discovery_service({"time": t.tolist(), "state": x.tolist()})
    assert result["status"] == "APPROVAL_REQUIRED"


@pytest.mark.parametrize("overrides,pattern", [
    ({"horizon": 0}, "positive"),
    ({"delta_fraction": -0.2}, "in"),
    ({"delta_fraction": 2.0}, "in"),
    ({"candidate_times": [0.5, float("inf")]}, "finite"),
])
def test_experiment_design_refuses_invalid_candidates(overrides, pattern):
    base = {"model_ir": ode(), "parameter": "k", "candidate_times": [0.5, 1.0], "horizon": 1.0}
    with pytest.raises(ValueError, match=pattern):
        svc.experiment_design_service({**base, **overrides})


def test_experiment_design_requires_explicit_heavy_approval():
    actual = svc.experiment_design_service({
        "model_ir": ode(), "parameter": "k", "candidate_times": [0.5, 1.0], "horizon": 1.0,
    })
    assert actual["status"] == "APPROVAL_REQUIRED"


def legacy_ode():
    """Known 0.9 IR requiring explicit user-authorized migration."""
    return {
        "name": "legacy", "domain": "physics", "model_family": "ode",
        "states": {"x": {"unit": "dimensionless", "initial": 1.0}},
        "parameters": [{"name": "k", "unit": "1/day", "value": 0.5}],
        "rhs": {"x": "-k*x"}, "independent_unit": "day",
    }


@pytest.mark.parametrize("service", [
    svc.model_plan_service,
    svc.model_validate_service,
    svc.model_simulate_service,
    svc.model_fit_service,
    svc.model_repair_service,
    svc.model_export_service,
    svc.model_stability_service,
    svc.model_validity_service,
    svc.experiment_design_service,
])
def test_ir_migration_requires_explicit_approval_in_every_service(service):
    result = service({"model_ir": legacy_ode()})
    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["action"] == "ir_migration"
    assert result["migration"]["from"] == "0.9"
    assert result["migration"]["required"] is True


def dimensionally_invalid_ode():
    model = ode()
    model["independent_unit"] = "day"
    model["parameters"][0]["unit"] = "dimensionless"
    return model


@pytest.mark.parametrize("service", [svc.model_simulate_service, svc.model_fit_service])
def test_model_with_inconsistent_physical_units_fails_before_solver(service):
    result = service({"model_ir": dimensionally_invalid_ode()})
    assert result["status"] == "FAIL"
    assert result["stage"] == "pre_validation"
    assert result["validation"]["status"] == "FAIL"


def test_invalid_simulated_validation_cannot_be_promoted_to_pass(monkeypatch):
    def invalid_validation(*args, **kwargs):
        return {"status": "PASS", "validation": {"status": "FAIL", "checks": [
            {"name": "regression", "status": "FAIL", "detail": "failed conservation invariant"},
        ]}}
    monkeypatch.setattr(svc, "simulate_model", invalid_validation)
    result = svc.model_simulate_service({"model_ir": ode(), "points": 10})
    assert result["status"] == "FAIL"
    assert result["validation"]["status"] == "FAIL"


def test_missing_covariance_never_becomes_invented_uncertainty(monkeypatch):
    monkeypatch.setattr(svc, "fit_ode_model", lambda *args, **kw: {
        "status": "TOOL_UNAVAILABLE", "covariance": None,
    })
    result = svc.model_fit_service({
        "model_ir": ode(), "time": [0, 1, 2], "observations": {"x": [1, 0.6, 0.3]},
    })
    assert result["status"] == "TOOL_UNAVAILABLE"
    assert "uncertainty_components" not in result
    assert result["provenance"]


def test_model_discovery_refuses_genuinely_inconsistent_sufficient_lengths():
    with pytest.raises(ValueError, match="lengths must match"):
        svc.model_discovery_service({"time": [0, 1, 2], "state": [0, 1, 2, 3]})


def test_executor_without_validation_block_keeps_output_unmodified(monkeypatch):
    # An adapter that does not supply verification metadata must not have
    # fabricated checks attached by the presentation/service layer.
    monkeypatch.setattr(svc, "simulate_model", lambda *args, **kw: {
        "status": "TOOL_UNAVAILABLE", "validation": None,
    })
    result = svc.model_simulate_service({"model_ir": ode(), "points": 10})
    assert result["status"] == "TOOL_UNAVAILABLE"
    assert result["validation"] is None
    assert "provenance" in result
