"""Isolated execution of generated scientific code (PHASE 1).

Generated code runs in a child process with a timeout, a private working
directory and captured streams. No shell is involved (argv, never
``shell=True``), so command injection through code strings is impossible.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field


@dataclass
class ExecutionRecord:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    timeout_s: float
    seed: int | None
    execution_time_s: float
    tool_versions: dict[str, str] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)


def _tool_versions() -> dict[str, str]:
    versions: dict[str, str] = {"python": sys.version.split()[0]}
    for mod in ("numpy", "scipy", "sympy"):
        try:
            module = __import__(mod)
            versions[mod] = str(getattr(module, "__version__", "unknown"))
        except ImportError:
            versions[mod] = "not-installed"
    return versions


def run_python(code: str, timeout_s: float = 60.0,
               seed: int | None = None) -> ExecutionRecord:
    """Execute a Python snippet in isolation and record everything."""
    env = dict(os.environ)
    if seed is not None:
        env["AXIOMIZE_SEED"] = str(seed)
        env["PYTHONHASHSEED"] = str(seed % 4294967296)
    start = time.perf_counter()
    timed_out = False
    try:
        with tempfile.TemporaryDirectory(prefix="axiomize_exec_") as workdir:
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True, text=True, timeout=timeout_s,
                cwd=workdir, env=env, check=False,
            )
        exit_code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = (exc.stderr or b"").decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    return ExecutionRecord(
        exit_code=exit_code, stdout=stdout, stderr=stderr,
        timed_out=timed_out, timeout_s=timeout_s, seed=seed,
        execution_time_s=time.perf_counter() - start,
        tool_versions=_tool_versions(),
    )
