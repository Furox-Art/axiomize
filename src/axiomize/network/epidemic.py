"""Network epidemic dynamics (PHASE 6).

Discrete-time chain-binomial SIR on a contact graph with explicit probability,
graph-size and work ceilings.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from axiomize.limits import MAX_ARRAY_ITEMS, MAX_RESULT_CELLS, bounded_int

MAX_NETWORK_NODES = 20_000
MAX_NETWORK_EDGES = MAX_ARRAY_ITEMS
MAX_NETWORK_STEPS = 10_000


def _probability(value: Any, *, name: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(out) or out < 0 or out > 1:
        raise ValueError(f"{name} must be finite and in [0, 1]")
    return out


def build_er_graph(n: int, p: float, seed: int = 0) -> Any:
    import networkx as nx

    n = bounded_int(n, name="network node count", minimum=1, maximum=MAX_NETWORK_NODES)
    p = _probability(p, name="edge probability")
    # Expected dense work is rejected before NetworkX allocates the graph.
    expected_edges = p * n * (n - 1) / 2
    if expected_edges > MAX_NETWORK_EDGES:
        raise ValueError(
            f"requested Erdos-Renyi graph has {expected_edges:.0f} expected edges, exceeding hard limit {MAX_NETWORK_EDGES}"
        )
    return nx.erdos_renyi_graph(n, p, seed=seed)


def _graph_size(graph: Any) -> tuple[int, int]:
    import networkx as nx

    try:
        n = int(nx.number_of_nodes(graph))
        m = int(nx.number_of_edges(graph))
    except Exception as exc:
        raise ValueError(f"graph must be a NetworkX-compatible graph: {exc}") from exc
    if n < 1 or n > MAX_NETWORK_NODES:
        raise ValueError(f"graph node count must be in 1..{MAX_NETWORK_NODES}")
    if m < 0 or m > MAX_NETWORK_EDGES:
        raise ValueError(f"graph edge count must be in 0..{MAX_NETWORK_EDGES}")
    return n, m


def heterogeneity_factor(graph: Any) -> float:
    """<k^2>/<k>: how much hubs amplify spread over homogeneous mixing."""
    import networkx as nx

    n, _ = _graph_size(graph)
    degrees = np.fromiter((d for _, d in nx.degree(graph)), dtype=float, count=n)
    mean = float(degrees.mean())
    value = float((degrees ** 2).mean() / mean) if mean > 0 else 1.0
    if not math.isfinite(value):
        raise RuntimeError("network heterogeneity factor is non-finite")
    return value


def sir_on_network(graph: Any, beta: float, gamma: float, I0: int,
                   max_steps: int = 365, seed: int = 0) -> dict[str, Any]:
    import networkx as nx

    n, edges = _graph_size(graph)
    beta = _probability(beta, name="beta")
    gamma = _probability(gamma, name="gamma")
    I0 = bounded_int(I0, name="I0", minimum=0, maximum=n)
    max_steps = bounded_int(max_steps, name="max_steps", minimum=0, maximum=MAX_NETWORK_STEPS)
    # Worst-case neighbor scanning is O(edges * steps). Keep direct calls within
    # the same bounded work envelope as other in-process scientific executors.
    work = max_steps * max(1, edges)
    if work > MAX_RESULT_CELLS:
        raise ValueError(
            f"network simulation worst-case work {work} exceeds hard limit {MAX_RESULT_CELLS} edge-steps"
        )

    rng = np.random.default_rng(seed)
    nodes = list(nx.nodes(graph))
    state = {v: "S" for v in nodes}
    if I0:
        for v in rng.choice(nodes, size=I0, replace=False):
            state[v] = "I"
    infected_curve = [I0]
    for _ in range(max_steps):
        new_infected, new_recovered = set(), set()
        for v in nodes:
            if state[v] != "I":
                continue
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
    recovered = sum(1 for v in nodes if state[v] == "R")
    return {
        "attack_rate": recovered / n,
        "peak": max(infected_curve),
        "steps": len(infected_curve) - 1,
        "heterogeneity_factor": heterogeneity_factor(graph),
    }
