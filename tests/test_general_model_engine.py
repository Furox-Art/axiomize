from __future__ import annotations

import json

import numpy as np
import pytest

from axiomize.application.general_services import (
    experiment_design_service,
    model_discovery_service,
    model_plan_service,
)
from axiomize.general_engine import (
    export_model,
    fit_ode_model,
    infer_domain,
    rank_model_fits,
    repair_model,
    simulate_model,
    validate_model,
)
from axiomize.model_ir import MigrationApprovalRequired, ModelIR, migration_preview


def decay_model(*, k: float = 0.5, fit: bool = False, constraint: float = 0.0) -> ModelIR:
    return ModelIR.from_dict({
        "schema_version": "1.0",
        "name": "exponential-decay",
        "domain": "physics",
        "family": "ode",
        "independent_variable": "t",
        "independent_unit": "day",
        "variables": [
            {"name": "x", "unit": "dimensionless", "initial": 1.0, "bounds": [0.0, None]},
        ],
        "parameters": [
            {"name": "k", "unit": "1/day", "value": k, "bounds": [0.0, 2.0], "fit": fit},
        ],
        "equations": [
            {"target": "x", "expression": "-k*x", "kind": "derivative"},
        ],
        "constraints": [
            {
                "name": "state_floor",
                "expression": "x",
                "relation": "ge",
                "threshold": constraint,
                "scientific_basis": "state is constrained to the admissible region",
            },
        ],
        "assumptions": ["first-order decay"],
    })


def test_ir_migration_is_never_silent() -> None:
    legacy = {
        "name": "legacy",
        "domain": "physics",
        "model_family": "ode",
        "states": {"x": {"unit": "dimensionless", "initial": 1.0}},
        "parameters": [{"name": "k", "unit": "1/day", "value": 1.0}],
        "rhs": {"x": "-k*x"},
        "independent_unit": "day",
    }
    preview = migration_preview(legacy)
    assert preview["required"] is True
    with pytest.raises(MigrationApprovalRequired):
        ModelIR.from_dict(legacy)

    migrated = ModelIR.from_dict(legacy, allow_migration=True)
    assert migrated.schema_version == "1.0"
    assert migrated.family.value == "ode"
    assert migrated.metadata["migration_history"]
    assert migrated.provenance[-1].action == "model_ir_migration"


def test_generic_ode_execution_and_visible_scientific_checks() -> None:
    model = decay_model(k=0.5)
    out = simulate_model(model, t_span=(0.0, 5.0), points=80)
    assert out["status"] == "PASS"
    assert out["solver"]["backend"] == "scipy"
    assert out["states"]["x"][-1] == pytest.approx(np.exp(-2.5), rel=3e-5)
    validation = out["validation"]
    assert validation["status"] == "PASS"
    check = next(c for c in validation["scientific_constraints"] if c["name"] == "state_floor")
    assert check["status"] == "PASS"
    assert check["scientific_basis"]


def test_constraint_failure_is_visible_and_repair_needs_consent() -> None:
    model = decay_model(k=0.5, constraint=0.9)
    out = simulate_model(model, t_span=(0.0, 5.0), points=80)
    assert out["status"] == "FAIL"
    validation = out["validation"]
    assert validation["repair_requires_approval"] is True
    assert validation["repair_proposal"]["preserve_failed_model"] is True

    blocked = repair_model(model, validation=validation)
    assert blocked["status"] == "APPROVAL_REQUIRED"
    approved = repair_model(model, approve=True, validation=validation)
    assert approved["status"] == "REBUILD_REQUIRED"
    assert approved["preserved_original"]["name"] == model.name
    assert approved["model"]["metadata"]["constraint_rebuild_approved"] is True


def test_fit_checks_identifiability_residuals_and_complexity() -> None:
    t = np.linspace(0.0, 4.0, 30)
    y = np.exp(-0.4 * t)
    model = decay_model(k=0.2, fit=True)
    fit = fit_ode_model(model, time=t.tolist(), observations={"x": y.tolist()})
    assert fit["status"] == "PASS"
    assert fit["parameters"]["k"] == pytest.approx(0.4, rel=2e-3)
    assert fit["identifiability"]["identifiable"] is True
    assert fit["residual_diagnostics"]["x"]["rmse"] < 1e-4
    assert set(fit["selection_scores"]) >= {"aic", "bic", "sse", "n", "k"}

    ranking = rank_model_fits({
        "simple": {"selection_scores": {"bic": 10.0, "aic": 9.0, "sse": 1.0}},
        "complex": {"selection_scores": {"bic": 15.0, "aic": 8.0, "sse": 0.9}},
    }, criterion="bic")
    assert ranking["winner"] == "simple"


def test_causal_claim_is_not_inferred_from_fit_alone() -> None:
    model = decay_model()
    model.metadata["causal_claim"] = True
    out = validate_model(model)
    causal = next(c for c in out["checks"] if c["name"] == "causal_identification")
    assert causal["status"] == "UNVERIFIED"
    assert "fit/correlation alone" in causal["detail"]


def test_export_is_portable_and_does_not_fake_standards() -> None:
    model = decay_model()
    exported = export_model(model, format="json")
    decoded = json.loads(exported["content"])
    assert decoded["schema_version"] == "1.0"
    assert decoded["family"] == "ode"

    py = export_model(model, format="python")
    assert "ModelIR.from_dict" in py["content"]
    sbml = export_model(model, format="sbml")
    assert sbml["status"] == "ADAPTER_REQUIRED"


def test_idea_planning_ranks_multiple_families_without_inventing_equations() -> None:
    domain = infer_domain("chemical reaction concentration with molecular noise")
    assert domain["domain"] == "chemistry"
    plan = model_plan_service({
        "idea": "chemical reaction concentration with molecular noise",
        "signals": ["stochastic"],
    })
    assert plan["status"] == "NEEDS_MODEL_IR"
    assert 2 <= len(plan["candidate_families"]) <= 3
    assert plan["candidate_families"][0]["family"] == "stochastic"


def test_heavy_discovery_and_experiment_design_require_approval() -> None:
    t = np.linspace(0.0, 2.0, 20)
    x = np.exp(-t)
    discovery = model_discovery_service({"time": t.tolist(), "state": x.tolist()})
    assert discovery["status"] == "APPROVAL_REQUIRED"

    model = decay_model().to_dict()
    design = experiment_design_service({
        "model_ir": model,
        "parameter": "k",
        "candidate_times": [0.5, 1.0, 2.0],
        "horizon": 2.0,
    })
    assert design["status"] == "APPROVAL_REQUIRED"


def test_general_model_cli_surface(tmp_path, capsys) -> None:
    from axiomize.cli import main

    request = tmp_path / "model.json"
    request.write_text(json.dumps({
        "model_ir": decay_model(k=0.5).to_dict(),
        "t_span": [0.0, 2.0],
        "points": 30,
    }), encoding="utf-8")
    rc = main(["model", "--action", "simulate", "--input-json", str(request)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert payload["states"]["x"][-1] == pytest.approx(np.exp(-1.0), rel=5e-5)


def test_general_model_mcp_surface() -> None:
    from axiomize.server import mcp_server

    names = {item["name"] for item in mcp_server.list_tools()}
    assert "axiomize.model_simulate" in names
    out = mcp_server._call_tool("axiomize.model_simulate", {
        "model_ir": decay_model(k=0.5).to_dict(),
        "t_span": [0.0, 1.0],
        "points": 20,
    })
    assert out["status"] == "PASS"


def test_general_model_rest_surface() -> None:
    import threading
    import urllib.request

    from axiomize.server.rest_server import start_server

    server = start_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = json.dumps({
            "model_ir": decay_model(k=0.5).to_dict(),
            "t_span": [0.0, 1.0],
            "points": 20,
        }).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/v1/simulate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["status"] == "PASS"
        assert payload["family"] == "ode"
    finally:
        server.shutdown()
        server.server_close()
