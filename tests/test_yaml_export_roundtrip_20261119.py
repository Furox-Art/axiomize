"""Real PyYAML round-trip for the yaml export path.

PyYAML is declared in both manifests now, so CI exercises the real serializer
instead of only the fake-module coverage path. Values and units must
round-trip exactly through ``yaml.safe_dump``/``yaml.safe_load``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from axiomize.general_engine import export_model
from axiomize.general_engine_core import export_model as core_export_model
from axiomize.model_ir import ModelIR

ROOT = Path(__file__).resolve().parents[1]


def _model() -> ModelIR:
    return ModelIR.from_dict({
        "schema_version": "1.0", "name": "yaml-roundtrip", "domain": "physics",
        "family": "ode", "independent_variable": "t", "independent_unit": "day",
        "variables": [
            {"name": "x", "unit": "dimensionless", "initial": 0.1234567890123456},
            {"name": "tiny", "unit": "1/day", "initial": 1e-300, "role": "output"},
        ],
        "parameters": [
            {"name": "k", "unit": "1/day", "value": 3.141592653589793},
        ],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    })


def test_yaml_export_round_trips_ir_exactly() -> None:
    model = _model()
    out = export_model(model, format="yaml")
    assert out["format"] == "yaml"
    parsed = yaml.safe_load(out["content"])
    assert parsed == model.to_dict()
    assert parsed["variables"][0]["initial"] == 0.1234567890123456
    assert parsed["variables"][1]["initial"] == 1e-300


def test_yaml_export_still_fail_closed_without_pyyaml(monkeypatch) -> None:
    import axiomize.general_engine_core as core

    monkeypatch.setattr(core, "_module_present", lambda name: False)
    out = core_export_model(_model(), format="yaml")
    assert out["status"] == "TOOL_UNAVAILABLE"
    assert "JSON" in out["detail"]


def test_pyyaml_is_declared_in_both_manifests() -> None:
    requirements = (ROOT / "requirements-test.txt").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "PyYAML" in requirements
    assert "PyYAML" in pyproject
