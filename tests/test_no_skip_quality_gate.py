"""Executable proof of the mandatory no-skip quality gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("test_case", "return_code"),
    [
        ("def test_ok():\\n    assert True\\n", 0),
        ("import pytest\\ndef test_skip():\\n    pytest.skip('missing optional dependency')\\n", 1),
    ],
)
def test_no_skip_gate_rejects_skips(
    tmp_path: Path,
    test_case: str,
    return_code: int,
) -> None:
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "conftest.py").write_text((root / "conftest.py").read_text())
    (tmp_path / "test_probe.py").write_text(test_case.replace("\\n", "\n"))
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rs", "test_probe.py"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert proc.returncode == return_code, proc.stdout + proc.stderr
    if return_code:
        assert "QUALITY GATE FAILED: 1 skipped test(s)" in proc.stdout


def test_ci_sets_up_required_node_in_python_test_jobs() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text()
    assert workflow.count("Set up Node.js for mandatory npm launcher contract tests") == 2
    assert workflow.count("actions/setup-node@820762786026740c76f36085b0efc47a31fe5020") >= 3
    assert "python -m pytest tests/ -q --cov=axiomize" in workflow
