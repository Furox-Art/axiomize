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
    tool_dir = repo_root / "skills" / "axiomize" / "tools"
    if tool_dir.is_dir():
        sys.path.insert(0, str(tool_dir))

    import parallel_sweep

    from axiomize.advanced_diagnostics import stopping_decision
    from axiomize.bayesian.mh import normal_mean_posterior
    from axiomize.json_safety import json_safe
    from axiomize.network.epidemic import build_er_graph, sir_on_network
    from axiomize.sensitivity.analysis import mc_sensitivity
    from axiomize.uncertainty.quantify import propagate

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
    set_order = json_safe({"zeta", "alpha", "mu", "beta"})
    if set_order != sorted(set_order):
        raise SystemExit(f"json_safe set order is not canonical: {set_order!r}")
    payload["json_safety"] = {"set_order": set_order}

    def _model(params: dict[str, float]) -> float:
        return params["a"] * 2.0 + params["b"] * 0.5

    forward_bounds = {"a": (0.0, 1.0), "b": (0.0, 1.0)}
    reverse_bounds = {"b": (0.0, 1.0), "a": (0.0, 1.0)}
    forward_sensitivity = mc_sensitivity(_model, forward_bounds, n=500, seed=20261024)
    reverse_sensitivity = mc_sensitivity(_model, reverse_bounds, n=500, seed=20261024)
    if reverse_sensitivity != forward_sensitivity:
        raise SystemExit("mc_sensitivity depends on caller mapping order")
    forward_uncertainty = propagate(_model, {"a": (1.0, 0.1), "b": (1.0, 0.1)}, n=500, seed=20261024)
    reverse_uncertainty = propagate(_model, {"b": (1.0, 0.1), "a": (1.0, 0.1)}, n=500, seed=20261024)
    if reverse_uncertainty != forward_uncertainty:
        raise SystemExit("propagate depends on caller mapping order")
    payload["parameter_order"] = {
        # BLAS reduction order differs per OS, so corrcoef moves in the last bits.
        "sensitivity": {name: round(value, 9) for name, value in forward_sensitivity.items()},
        "uncertainty": {name: round(value, 9) for name, value in forward_uncertainty.items()},
    }

    mc_tasks = parallel_sweep._mc_tasks(0.3, 0.1, 1, 2000, 6)
    payload["monte_carlo"] = {
        "tasks": [list(task) for task in mc_tasks],
        "extinct": sum(parallel_sweep.gillespie_chunk(task) for task in mc_tasks),
    }
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
