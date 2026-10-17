"""CI must measure both line and branch coverage with a nontrivial floor."""

from __future__ import annotations

from pathlib import Path


def test_default_coverage_includes_branch_paths_and_enforces_ratchet_floor():
    root = Path(__file__).resolve().parents[1]
    config = (root / "pyproject.toml").read_text()
    run_section = config.split("[tool.coverage.run]", 1)[1].split("[tool.coverage.report]", 1)[0]
    report_section = config.split("[tool.coverage.report]", 1)[1].split("[tool.ruff]", 1)[0]
    assert "branch = true" in run_section
    floor_lines = [line for line in report_section.splitlines() if line.startswith("fail_under = ")]
    assert len(floor_lines) == 1
    assert float(floor_lines[0].split("=", 1)[1]) >= 83.0


def test_ci_does_not_drop_branch_coverage_or_real_backend_gates():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/ci.yml").read_text()
    backends = (root / ".github/workflows/scientific-backends.yml").read_text()
    assert "--cov-branch" in workflow
    for job in ["real-jax", "real-pymc", "real-lean"]:
        assert f"  {job}:" in backends
