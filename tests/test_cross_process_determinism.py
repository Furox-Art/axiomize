"""Cross-process determinism: seeded scientific results must be byte-stable.

Two fresh interpreters run the same posterior/network/stopping workload with
different ``PYTHONHASHSEED`` values. Any dependence on hash-seed ordering in
the diagnostics or sampling paths changes the output and fails the gate.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CHILD = r'''
import json
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
sys.path.insert(0, str(repo_root / "src"))

from axiomize.advanced_diagnostics import stopping_decision
from axiomize.bayesian.mh import normal_mean_posterior
from axiomize.json_safety import json_safe
from axiomize.network.epidemic import build_er_graph, sir_on_network

posterior = normal_mean_posterior(
    [1.0, 1.1, 0.9, 1.05, 0.95, 1.02],
    sigma=0.2,
    n_samples=2_000,
    burn=500,
    seed=20261024,
)
graph = build_er_graph(n=40, p=0.1, seed=20261024)
epidemic = sir_on_network(graph, beta=0.3, gamma=0.1, I0=3, max_steps=30, seed=20261024)
decision = stopping_decision(
    [1.0, 0.5, 0.25, 0.125, 0.0625],
    relative_tolerance=0.1,
    absolute_tolerance=1e-9,
    patience=2,
    budget_used=8,
    budget_limit=10,
    uncertainty=0.05,
    uncertainty_target=0.1,
)
payload = {
    "posterior": posterior,
    "epidemic": epidemic,
    "decision": decision,
    "set_order": json_safe({"zeta", "alpha", "mu", "beta"}),
}
print(json.dumps(payload, ensure_ascii=False))
'''


@cache
def _run_with_hash_seed(seed: str) -> str:
    env = {
        **os.environ,
        "PYTHONHASHSEED": seed,
        "PYTHONIOENCODING": "utf-8",
    }
    completed = subprocess.run(
        [sys.executable, "-c", CHILD, str(REPO_ROOT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def test_workload_is_byte_identical_across_hash_seeds() -> None:
    first = _run_with_hash_seed("0")
    second = _run_with_hash_seed("12345")
    assert first.strip()
    assert first.strip() == second.strip()


def test_workload_exercises_non_empty_results() -> None:
    payload = json.loads(_run_with_hash_seed("0"))
    posterior = payload["posterior"]
    assert len(posterior["ci95"]) == 2
    assert posterior["ci95"][0] <= posterior["mean"] <= posterior["ci95"][1]
    assert 0.0 <= posterior["acceptance_rate"] <= 1.0
    assert payload["epidemic"]["steps"] > 0
    assert payload["decision"]["decision"] == "STOP"
    assert payload["decision"]["reasons"] == ["uncertainty_target"]
    assert payload["decision"]["checks"], "stopping decision produced no criteria"
    assert payload["set_order"] == ["alpha", "beta", "mu", "zeta"]
