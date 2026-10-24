"""Deterministic axiomize workload sampled by the determinism matrix."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source_dir = repo_root / "src"
    if source_dir.is_dir():
        sys.path.insert(0, str(source_dir))

    from axiomize.advanced_diagnostics import stopping_decision
    from axiomize.bayesian.mh import normal_mean_posterior
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
    payload = {"posterior": posterior, "epidemic": epidemic, "decision": decision}
    if not payload["epidemic"]["steps"] or not payload["decision"]["checks"]:
        raise SystemExit("workload produced empty results; it is vacuous")
    artifact_dir = os.environ.get("DETERMINISM_ARTIFACT_DIR")
    if artifact_dir:
        Path(artifact_dir, "payload.json").write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
            newline="\n",
        )
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
