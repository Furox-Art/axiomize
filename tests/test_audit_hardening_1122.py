"""Regression coverage for the 1.12.2 repository-audit fixes."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from axiomize.limits import (
    MAX_INTEGER_DIGITS,
    bounded_float,
    bounded_int,
    enforce_finite_values,
)
from axiomize.runs.state import RunState

ROOT = Path(__file__).resolve().parents[1]


def _release_contract_module():
    path = ROOT / ".github" / "scripts" / "check_release_contract.py"
    spec = importlib.util.spec_from_file_location("axiomize_release_contract_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shared_numeric_boundaries_reject_booleans_and_huge_integer_text() -> None:
    with pytest.raises(ValueError, match="boolean"):
        bounded_float(True, name="alpha")
    with pytest.raises(ValueError, match="boolean"):
        enforce_finite_values([1.0, False], name="values")
    huge = "9" * (MAX_INTEGER_DIGITS + 1)
    with pytest.raises(ValueError, match="exceeds"):
        bounded_int(huge, name="count", maximum=10)


@pytest.mark.parametrize("declared_version", [True, 1.5, "1.5"])
def test_run_state_rejects_nonexact_manifest_versions(tmp_path: Path, declared_version) -> None:
    RunState(problem_definition="manifest-version-audit").save(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["run_format_version"] = declared_version
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        RunState.load(tmp_path)


def test_release_contract_keeps_package_trigger_readme_and_changelog_in_lockstep(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _release_contract_module()
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_WORKFLOW", raising=False)
    monkeypatch.delenv("GITHUB_REF", raising=False)
    assert module.main() == 0


def test_release_workflow_ref_guard_blocks_feature_branch_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _release_contract_module()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_WORKFLOW", "Release")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/audit/not-main")
    assert module.main() == 1


def test_release_workflow_ref_guard_allows_main(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _release_contract_module()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_WORKFLOW", "Release")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    assert module.main() == 0
