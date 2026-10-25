"""Worker-count invariance for the parallel Monte Carlo skill tool.

``--job mc`` split a fixed run budget across the configured worker count and
seeded each chunk independently, so the same command reported a different
fade-out probability on a 2-core runner than on an 8-core laptop. Each run now
derives its stream from a global run index and the chunk layout is fixed, which
makes the aggregate independent of how the pool is sized.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills" / "axiomize" / "tools" / "parallel_sweep.py"


def _sweep_module():
    spec = importlib.util.spec_from_file_location("axiomize_parallel_sweep_invariance", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixed_chunks_cover_every_run_exactly_once() -> None:
    module = _sweep_module()
    for total in (1, 49, 50, 51, 120, 400):
        tasks = module._mc_tasks(0.3, 0.1, 1, 5000, total)
        covered = []
        for task in tasks:
            start, count = task[4], task[5]
            covered.extend(range(start, start + count))
        assert covered == list(range(total))
        assert all(task[5] <= module.MC_CHUNK_RUNS for task in tasks)


def test_run_stream_depends_only_on_global_index() -> None:
    module = _sweep_module()
    whole = module.gillespie_chunk((0.3, 0.1, 1, 500, 0, 8, module.MC_SEED))
    left = module.gillespie_chunk((0.3, 0.1, 1, 500, 0, 3, module.MC_SEED))
    right = module.gillespie_chunk((0.3, 0.1, 1, 500, 3, 5, module.MC_SEED))
    assert whole == left + right


def test_cli_aggregate_does_not_move_with_worker_count(tmp_path: Path) -> None:
    child = tmp_path / "mc_invariance_child.py"
    child.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(TOOL.parent)!r})\n"
        "import parallel_sweep\n"
        "if __name__ == '__main__':\n"
        "    for workers in (1, 3):\n"
        "        parallel_sweep.job_mc(workers, total_runs=120)\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(child)],
        capture_output=True,
        text=True,
        check=True,
    )
    values = re.findall(r"observed = ([0-9.]+)", completed.stdout)
    assert len(values) == 2, completed.stdout
    assert values[0] == values[1], completed.stdout
