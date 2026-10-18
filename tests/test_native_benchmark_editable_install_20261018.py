"""Prove the native wheel benchmark works from a source/ editable install too.

An editable checkout must not rely on pytest conftest for skill-tool imports.
All 12 cases invoke real scientific executors, not a mock or proxy model.
"""

from __future__ import annotations

import subprocess
import sys

from axiomize import benchmark_suite


def test_complete_package_native_benchmark_has_real_passes():
    report = benchmark_suite.run_suite()
    assert report["total"] == 12
    assert report["passed"] == 12, report
    assert report["status"] == "PASS"
    assert all(item["status"] == "PASS" for item in report["results"])


def test_fresh_python_process_resolves_wheel_included_tool_without_pytest_bootstrap(tmp_path):
    script = (
        "from axiomize.tools.validate import gillespie_sir_once; "
        "from numpy.random import default_rng; "
        "out = gillespie_sir_once(0.3,0.1,1,5000,rng=default_rng(9)); "
        "assert isinstance(out[\"extinct_early\"], bool)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path,
        text=True, capture_output=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr
