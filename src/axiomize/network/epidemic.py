"""Network epidemic dynamics (PHASE 6).

Discrete-time chain-binomial SIR on a contact graph: heterogeneous
degree structure the compartmental model cannot see.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def build_er_graph(n: int, p: float, seed: int = 0) -> Any:
    import networkx as nx

    return nx.erdos_renyi_graph(n, p, seed=seed)


def heterogeneity_factor(graph: Any) -> float:
    """<k^2>/<k>: how much hubs amplify spread over homogeneous mixing."""
    import networkx as nx

    degrees = np.array([d for _, d in nx.degree(graph)], dtype=float)
    mean = degrees.mean()
    return float((degrees ** 2).mean() / mean) if mean > 0 else 1.0


def sir_on_network(graph: Any, beta: float, gamma: float, I0: int,
                   max_steps: int = 365, seed: int = 0) -> dict[str, Any]:
    import networkx as nx

    rng = np.random.default_rng(seed)
    nodes = list(nx.nodes(graph))
    state = {v: "S" for v in nodes}
    for v in rng.choice(nodes, size=min(I0, len(nodes)), replace=False):
        state[v] = "I"
    infected_curve = [sum(1 for v in nodes if state[v] == "I")]
    for _ in range(max_steps):
        new_infected, new_recovered = set(), set()
        for v in nodes:
            if state[v] == "I":
                if rng.random() < gamma:
                    new_recovered.add(v)
                else:
                    for w in nx.neighbors(graph, v):
                        if state[w] == "S" and rng.random() < beta:
                            new_infected.add(w)
        for v in new_infected:
            state[v] = "I"
        for v in new_recovered:
            state[v] = "R"
        infected_curve.append(sum(1 for v in nodes if state[v] == "I"))
        if infected_curve[-1] == 0:
            break
    n = len(nodes)
    recovered = sum(1 for v in nodes if state[v] == "R")
    return {"attack_rate": recovered / n, "peak": max(infected_curve),
            "steps": len(infected_curve) - 1,
            "heterogeneity_factor": heterogeneity_factor(graph)}
