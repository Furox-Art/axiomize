"""JSON/Python exports must carry an explicit status (README format table).

Every other export format already reports ``status``; the canonical JSON and
rerunnable Python exports returned only ``format``/``content``, so a caller
applying the documented ``status == "PASS"`` gate to them saw a KeyError or a
silent None. The README export table promises PASS for both.
"""

from __future__ import annotations

import json

from axiomize.general_engine import export_model
from axiomize.general_engine_core import export_model as core_export_model
from axiomize.model_ir import ModelIR


def _model() -> ModelIR:
    return ModelIR.from_dict({
        "schema_version": "1.0", "name": "status-export", "domain": "physics",
        "family": "ode", "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
        "parameters": [{"name": "k", "unit": "1/day", "value": 0.5}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    })


def test_json_export_reports_pass_status() -> None:
    out = export_model(_model(), format="json")
    assert out["status"] == "PASS"
    assert out["format"] == "json"
    assert json.loads(out["content"])["name"] == "status-export"


def test_python_export_reports_pass_status() -> None:
    out = export_model(_model(), format="python")
    assert out["status"] == "PASS"
    assert out["format"] == "python"
    assert "ModelIR.from_dict" in out["content"]


def test_core_export_status_matches_facade() -> None:
    for fmt in ("json", "python"):
        assert core_export_model(_model(), format=fmt)["status"] == "PASS"


def test_non_success_export_statuses_are_unchanged() -> None:
    assert export_model(_model(), format="sbml")["status"] == "ADAPTER_REQUIRED"
    assert export_model(_model(), format="cellml")["status"] == "ADAPTER_REQUIRED"
