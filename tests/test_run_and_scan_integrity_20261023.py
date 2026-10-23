"""Regressions: validity scans must not report false PASS, run loads fail closed."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from axiomize import general_engine_core as core
from axiomize.model_ir import ModelIR
from axiomize.runs.state import RunState


def decay() -> ModelIR:
    return ModelIR.from_dict({
        "schema_version": "1.0", "domain": "physics", "name": "physical-decay",
        "family": "ode", "independent_variable": "t",
        "variables": [{"name": "x", "initial": 1.0}],
        "parameters": [{"name": "k", "value": 0.4}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    })


def test_validity_scan_reports_fail_when_every_simulation_fails(monkeypatch):
    monkeypatch.setattr(core, "simulate_model", lambda *args, **kwargs: {"status": "FAIL"})
    result = core.validity_scan(
        decay(), parameter="k", values=[0.0, 0.5],
        t_span=(0.0, 1.0), points=14, approve_heavy=True,
    )
    assert result["status"] == "FAIL"
    assert result["valid_interval_observed"] is None


def test_validity_scan_reports_fail_when_one_simulation_fails(monkeypatch):
    def fake_simulate(model, *, parameter_overrides=None, **kwargs):
        if parameter_overrides and parameter_overrides.get("k") == 0.5:
            return {"status": "PASS", "validation": {"status": "FAIL"}}
        return {"status": "PASS", "validation": {"status": "PASS"}}

    monkeypatch.setattr(core, "simulate_model", fake_simulate)
    result = core.validity_scan(
        decay(), parameter="k", values=[0.0, 0.5],
        t_span=(0.0, 1.0), points=14, approve_heavy=True,
    )
    assert result["status"] == "FAIL"
    assert result["valid_interval_observed"] == [0.0, 0.0]


def test_run_state_import_reports_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot read run-state file"):
        RunState.import_file(tmp_path / "absent.json")


def test_run_state_load_requires_manifest(tmp_path: Path) -> None:
    RunState(problem_definition="missing-manifest").save(tmp_path)
    (tmp_path / "manifest.json").unlink()
    with pytest.raises(ValueError, match="regular manifest.json"):
        RunState.load(tmp_path)


@pytest.mark.parametrize("manifest", [{}, {"run_sha256": "0" * 64}])
def test_run_state_load_requires_integrity_fields(tmp_path: Path, manifest) -> None:
    RunState(problem_definition="stripped-manifest").save(tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="required integrity fields"):
        RunState.load(tmp_path)


def test_run_state_load_rejects_symlinked_manifest(tmp_path: Path) -> None:
    RunState(problem_definition="symlinked-manifest").save(tmp_path)
    external = tmp_path / "manifest-outside.json"
    external.write_text((tmp_path / "manifest.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "manifest.json").unlink()
    try:
        (tmp_path / "manifest.json").symlink_to(external)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    with pytest.raises(ValueError, match="regular manifest.json"):
        RunState.load(tmp_path)


def test_run_state_load_rejects_symlinked_run_payload(tmp_path: Path) -> None:
    RunState(problem_definition="symlinked-run").save(tmp_path)
    external = tmp_path / "run-outside.json"
    external.write_text((tmp_path / "run.json").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "run.json").unlink()
    try:
        (tmp_path / "run.json").symlink_to(external)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    with pytest.raises(ValueError, match="regular run.json"):
        RunState.load(tmp_path)
