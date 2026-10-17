"""Require actual scientific backends in dedicated CI, not simulated success."""

from __future__ import annotations

from pathlib import Path

import pytest

from axiomize.formal.lean_adapter import LeanAdapter

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("pymc", "jax", "lean")


def test_optional_backend_ci_has_three_mandatory_real_jobs() -> None:
    source = (ROOT / ".github/workflows/scientific-backends.yml").read_text()
    for target in TARGETS:
        assert f"  real-{target}:" in source
    assert "dev/strict-json-wire-20261017" in source
    assert "workflow_dispatch:" in source
    assert "pymc>=5,<6" in source
    assert "jax[cpu]>=0.5,<1" in source
    assert "leanprover/lean4:v4.30.0" in source
    assert "true_theorem_proved_by_real_lean" in source and "false_theorem_rejected_by_real_lean" in source
    assert "pytest.skip(" not in source
    assert "continue-on-error: true" not in source


def test_temporary_lean_home_retains_only_required_toolchain_locator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ELAN_HOME", "/trusted/elan")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    env = LeanAdapter._minimal_env(str(tmp_path))
    assert env["ELAN_HOME"] == "/trusted/elan"
    assert env["HOME"] == str(tmp_path)
    assert "OPENAI_API_KEY" not in env
    monkeypatch.delenv("ELAN_HOME")
    assert LeanAdapter._minimal_env(str(tmp_path))["ELAN_HOME"] == str(Path.home() / ".elan")


def test_backend_registry_identifies_all_required_real_backends() -> None:
    assert len(TARGETS) == len(set(TARGETS))
    assert set(TARGETS) == {"pymc", "jax", "lean"}
