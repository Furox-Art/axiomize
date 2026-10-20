"""Round-2 coverage hardening: services, policy, standards and runtime hooks."""

from __future__ import annotations

import math
import re
import runpy
import sys
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import numpy as np
import pytest

import axiomize.cli as cli
import axiomize.limits as limits
import axiomize.portable_export_compat as compat
import axiomize.standards_export as standards_export
import axiomize.v120_runtime as runtime
from axiomize import advanced_diagnostics as advanced
from axiomize.fitting.estimator import FitResult
from axiomize.model_ir import ModelFamily, ModelIR
from axiomize.routing import router
from axiomize.scientific_stress import _models
from axiomize.server import mcp_server
from axiomize.uncertainty.quantify import confidence_intervals
from axiomize.validation import ledger
from axiomize.workflow.policy import ExecutionPermissions, RigorLevel, recommend_rigor

# ---------------------------------------------------------------------------
# Advanced diagnostics routing and scan aggregation
# ---------------------------------------------------------------------------


def test_uncertainty_propagation_routes_unsupported_families() -> None:
    result = advanced.propagate_parameter_uncertainty(
        SimpleNamespace(family=ModelFamily.NETWORK),
        t_span=(0.0, 1.0),
        parameter_uncertainty={},
    )
    assert result["status"] == "TOOL_ROUTE_REQUIRED"
    assert result["family"] == "network"
    assert "native executor" in result["detail"]


def test_equilibrium_guess_defaults_to_one_when_state_has_no_initial() -> None:
    model = SimpleNamespace(
        variables=[SimpleNamespace(name="x", role="state", initial=None)],
        parameters=[SimpleNamespace(name="k")],
        independent_variable="t",
        equations=[SimpleNamespace(target="x", kind="derivative", expression="k - x")],
    )
    equilibrium = advanced._equilibrium_for_ode(model, parameter_values={"k": 4.0})
    assert equilibrium["x"] == pytest.approx(4.0)


def test_bifurcation_scan_routes_non_ode_families() -> None:
    result = advanced.bifurcation_scan(
        SimpleNamespace(family=ModelFamily.ALGEBRAIC), parameter="p", values=[1.0, 2.0]
    )
    assert result["status"] == "TOOL_ROUTE_REQUIRED"
    assert result["family"] == "algebraic"
    assert "ODE Model IR" in result["detail"]


def test_bifurcation_scan_records_stability_transition_candidates(monkeypatch) -> None:
    model = SimpleNamespace(
        family=ModelFamily.ODE,
        variables=[],
        parameters=[SimpleNamespace(name="p", value=1.0, bounds=None)],
    )
    monkeypatch.setattr(
        advanced,
        "_equilibrium_for_ode",
        lambda model, *, parameter_values, guess: {"x": parameter_values["p"]},
    )
    monkeypatch.setattr(
        advanced,
        "local_stability",
        lambda model, *, state, parameter_overrides: {"max_real_part": state["x"] - 1.5},
    )
    result = advanced.bifurcation_scan(
        model, parameter="p", values=[0.5, 1.5, 0.0], approve_heavy=True
    )
    assert result["status"] == "PASS"
    assert [row["status"] for row in result["rows"]] == ["PASS", "PASS", "PASS"]
    transitions = result["transition_candidates"]
    assert len(transitions) == 2
    assert transitions[0]["between"] == [0.5, 1.5]
    assert transitions[1]["between"] == [1.5, 0.0]
    assert all(
        item["classification"] == "local_stability_transition_candidate"
        for item in transitions
    )


# ---------------------------------------------------------------------------
# Workflow policy
# ---------------------------------------------------------------------------


def test_rigor_level_parse_rejects_unknown_labels() -> None:
    with pytest.raises(ValueError, match="rigor must be weak/medium/strong"):
        RigorLevel.parse("extreme")


def test_permissions_ignore_unguarded_actions() -> None:
    permissions = ExecutionPermissions()
    assert permissions.requires_approval("visualize") is False
    assert permissions.requires_approval("heavy_compute") is True


def test_single_escalation_signal_stays_medium_with_an_explicit_reason() -> None:
    recommendation = recommend_rigor({"high_stakes": True})
    assert recommendation["level"] == RigorLevel.MEDIUM.value
    assert recommendation["reasons"][0] == "high-stakes consequence"
    assert recommendation["reasons"][-1] == (
        "one escalation signal is present; medium keeps cost bounded while adding checks"
    )


# ---------------------------------------------------------------------------
# CellML export unit de-duplication and algebraic CI targets
# ---------------------------------------------------------------------------


def test_cellml_duplicate_custom_unit_is_emitted_once() -> None:
    payload = _models()[ModelFamily.ALGEBRAIC].to_dict()
    payload["independent_unit"] = "1/min"
    payload["variables"][0]["unit"] = "1/minute"
    output = standards_export.export_cellml_2(ModelIR.from_dict(payload))
    assert output["status"] == "PASS"
    root = ET.fromstring(output["content"])
    ns = {"cellml": "http://www.cellml.org/cellml/2.0#"}
    names = [node.attrib.get("name") for node in root.findall(".//cellml:units", ns)]
    assert names.count("per_minute") == 1


def test_cellml_non_residual_algebraic_equation_keeps_declared_target() -> None:
    payload = _models()[ModelFamily.ALGEBRAIC].to_dict()
    payload["equations"] = [{"target": "x", "expression": "x - 2", "kind": "observation"}]
    output = standards_export.export_cellml_2(ModelIR.from_dict(payload))
    assert output["status"] == "PASS"
    root = ET.fromstring(output["content"])
    ns = {"math": "http://www.w3.org/1998/Math/MathML"}
    ci_values = [node.text for node in root.findall(".//math:ci", ns)]
    assert "x" in ci_values


# ---------------------------------------------------------------------------
# MCP dispatch edges
# ---------------------------------------------------------------------------


def test_mcp_visualization_requires_a_string_chart_type(tmp_path) -> None:
    with pytest.raises(ValueError, match="chart_type must be a string"):
        mcp_server._call_tool(
            "axiomize.model_visualize",
            {"run_dir": "recorded", "chart_type": 1},
            run_root=tmp_path,
        )


def test_mcp_fit_model_defaults_to_the_logistic_service() -> None:
    t = np.linspace(0.0, 10.0, 35)
    y = 15.0 / (1.0 + np.exp(-0.9 * (t - 5.0)))
    result = mcp_server._call_tool(
        "axiomize.fit_model", {"t": t.tolist(), "y": y.tolist()}
    )
    assert result["success"] is True
    assert result["method"] == "bounded_least_squares"
    assert math.isfinite(result["K"])
    assert result["K"] == pytest.approx(15.0, rel=0.05)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def test_cli_module_entry_point_exits_after_main(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["axiomize", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(cli.__file__, run_name="__main__")
    assert excinfo.value.code == 0


# ---------------------------------------------------------------------------
# Portable export compatibility and runtime installation hooks
# ---------------------------------------------------------------------------


def test_notebook_schema_alias_installation_is_idempotent() -> None:
    compat.install_notebook_schema_alias()
    installed = standards_export.export_notebook
    compat.install_notebook_schema_alias()
    assert standards_export.export_notebook is installed
    assert installed.__axiomize_schema_alias__ is True


def test_runtime_install_is_a_noop_when_already_installed() -> None:
    engine = SimpleNamespace(_AXIOMIZE_112_INSTALLED=True)
    advanced_api = SimpleNamespace()
    runtime.install(engine, advanced_api)
    assert not hasattr(engine, "select_solver")
    assert not hasattr(advanced_api, "_infer_bayesian")


# ---------------------------------------------------------------------------
# Router, uncertainty and integer parsing edges
# ---------------------------------------------------------------------------


def test_router_rejects_non_sequence_signals() -> None:
    with pytest.raises(ValueError, match="signals must be a sequence of strings"):
        router.classify({"signals": "beta"})


def test_confidence_intervals_reject_too_many_fit_parameters() -> None:
    fit = FitResult(
        params={f"p{index}": (1.0, 0.1) for index in range(limits.MAX_MODEL_PARAMETERS + 1)},
        rmse=0.0,
        aic=0.0,
        bic=0.0,
        resid_autocorr=0.0,
        success=True,
        method="probe",
        n=10,
        k=1,
    )
    with pytest.raises(ValueError, match="fit parameter count exceeds hard limit"):
        confidence_intervals(fit)


def test_bounded_int_reports_integer_conversion_failures(monkeypatch) -> None:
    monkeypatch.setattr(limits, "_INTEGER_TEXT", re.compile(r"^.*$"))
    with pytest.raises(ValueError, match="count must be an integer"):
        limits.bounded_int("abc", name="count", maximum=10)


def test_ledger_string_evidence_without_a_status_raises(monkeypatch) -> None:
    monkeypatch.setattr(ledger, "_coerce_status", lambda value: None)
    with pytest.raises(ValueError, match="bilinmeyen status"):
        ledger._normalize_evidence("experiment", "probe")
