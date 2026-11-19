"""Sweep child exit codes and stderr must be visible; BLAS threading capped.

Root cause of the worker-count invariance flake: under full-suite memory
pressure, spawned pool workers aborted with "OpenBLAS error: Memory
allocation still failed after 10 retries" -> BrokenProcessPool -> child exit
1, and the traceback was swallowed by ``capture_output=True, check=True``.
The tool now caps BLAS threads before numpy import (fresh spawn workers
re-import it), the child propagates ``job_mc``'s return code, and failures
surface stderr instead of hiding it.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills" / "axiomize" / "tools" / "parallel_sweep.py"


def _sweep_module():
    spec = importlib.util.spec_from_file_location("axiomize_parallel_sweep_exit_test", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_child(source: str, tmp_path: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    child = tmp_path / "sweep_child.py"
    child.write_text(source, encoding="utf-8")
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, str(child)], capture_output=True, text=True, env=merged, check=False,
    )


@pytest.mark.parametrize("job,code", [("mc", 0), ("mc", 1), ("sweep", 0), ("sweep", 1)])
def test_main_reflects_job_return_code(monkeypatch, job: str, code: int) -> None:
    module = _sweep_module()
    monkeypatch.setattr(module, "job_mc", lambda workers, total_runs=400: code)
    monkeypatch.setattr(module, "job_sweep", lambda workers: code)
    monkeypatch.setattr(sys, "argv", ["parallel_sweep.py", "--job", job])
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == code


def test_mc_sanity_failure_exits_nonzero_with_visible_output(tmp_path: Path) -> None:
    # A picklable zero-count chunk forces the theory sanity check to FAIL.
    # main() must turn that into exit 1, and the FAIL must be visible.
    source = (
        "import sys\n"
        f"sys.path.insert(0, {str(TOOL.parent)!r})\n"
        "import parallel_sweep\n"
        "def zero_chunk(args):\n"
        "    return 0\n"
        "if __name__ == '__main__':\n"
        "    parallel_sweep.gillespie_chunk = zero_chunk\n"
        "    sys.argv = ['parallel_sweep.py', '--job', 'mc', '--workers', '1']\n"
        "    parallel_sweep.main()\n"
    )
    completed = _run_child(source, tmp_path)
    assert completed.returncode == 1, f"stdout={completed.stdout}\nstderr={completed.stderr}"
    assert "sanity check -> FAIL" in completed.stdout


def test_blas_threads_capped_in_fresh_interpreter(tmp_path: Path) -> None:
    source = (
        "import os, sys\n"
        f"sys.path.insert(0, {str(TOOL.parent)!r})\n"
        "for var in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):\n"
        "    os.environ.pop(var, None)\n"
        "import parallel_sweep\n"
        "print(os.environ['OPENBLAS_NUM_THREADS'], os.environ['OMP_NUM_THREADS'],\n"
        "      os.environ['MKL_NUM_THREADS'], os.environ['NUMEXPR_NUM_THREADS'])\n"
    )
    completed = _run_child(source, tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.split() == ["1", "1", "1", "1"]


def test_blas_cap_respects_explicit_user_setting(tmp_path: Path) -> None:
    source = (
        "import os, sys\n"
        f"sys.path.insert(0, {str(TOOL.parent)!r})\n"
        "import parallel_sweep\n"
        "print(os.environ['OPENBLAS_NUM_THREADS'])\n"
    )
    completed = _run_child(source, tmp_path, env={"OPENBLAS_NUM_THREADS": "4"})
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "4"


def test_spawned_workers_inherit_the_blas_cap(tmp_path: Path) -> None:
    # The actual flake mechanism: workers are fresh spawn interpreters. The
    # cap must be in their environment before numpy loads there.
    source = (
        "import os, sys\n"
        f"sys.path.insert(0, {str(TOOL.parent)!r})\n"
        "import parallel_sweep\n"
        "from concurrent.futures import ProcessPoolExecutor\n"
        "def probe_chunk(_):\n"
        "    return os.environ.get('OPENBLAS_NUM_THREADS', 'unset')\n"
        "if __name__ == '__main__':\n"
        "    with ProcessPoolExecutor(max_workers=2) as ex:\n"
        "        print(list(ex.map(probe_chunk, [0, 1])))\n"
    )
    completed = _run_child(source, tmp_path, env={"OPENBLAS_NUM_THREADS": ""})
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "['1', '1']"
