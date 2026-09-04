"""Matplotlib scientific visualizations used by the adaptive workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def _prepare_output(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def plot_sensitivity(scores: dict[str, float], path: str | Path,
                     *, title: str = "Parameter sensitivity") -> Path:
    """Create a ranked horizontal sensitivity chart."""
    if not scores:
        raise ValueError("scores must not be empty")
    import matplotlib.pyplot as plt

    ranked = sorted(((str(k), float(v)) for k, v in scores.items()),
                    key=lambda item: abs(item[1]))
    names = [name for name, _ in ranked]
    values = [value for _, value in ranked]
    target = _prepare_output(path)
    fig, ax = plt.subplots()
    ax.barh(names, values)
    ax.set_xlabel("Sensitivity score")
    ax.set_title(title)
    ax.axvline(0.0, linewidth=0.8)
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)
    return target


def plot_surface_3d(x: Any, y: Any, z: Any, path: str | Path,
                    *, xlabel: str = "x", ylabel: str = "y", zlabel: str = "response",
                    title: str = "Response surface") -> Path:
    """Plot a 3D response surface from 1D axes and a 2D response array."""
    import matplotlib.pyplot as plt

    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    z_arr = np.asarray(z, dtype=float)
    if x_arr.ndim != 1 or y_arr.ndim != 1:
        raise ValueError("x and y must be one-dimensional")
    if z_arr.shape != (len(y_arr), len(x_arr)):
        raise ValueError("z shape must be (len(y), len(x))")
    if not np.all(np.isfinite(x_arr)) or not np.all(np.isfinite(y_arr)) or not np.all(np.isfinite(z_arr)):
        raise ValueError("x, y and z must be finite")

    xx, yy = np.meshgrid(x_arr, y_arr)
    target = _prepare_output(path)
    fig = plt.figure()
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(xx, yy, z_arr)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_zlabel(zlabel)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)
    return target


def plot_dependency_graph(nodes: list[str], edges: list[tuple[str, str]],
                          path: str | Path, *, title: str = "Model dependency graph") -> Path:
    """Plot a directed variable/mechanism dependency graph."""
    if not nodes:
        raise ValueError("nodes must not be empty")
    import matplotlib.pyplot as plt
    import networkx as nx

    graph = nx.DiGraph()
    graph.add_nodes_from(str(node) for node in nodes)
    graph.add_edges_from((str(a), str(b)) for a, b in edges)
    unknown = set(graph.nodes) - set(str(node) for node in nodes)
    if unknown:
        raise ValueError(f"edges reference undeclared nodes: {sorted(unknown)}")

    target = _prepare_output(path)
    fig, ax = plt.subplots()
    pos = nx.spring_layout(graph, seed=0)
    nx.draw_networkx(graph, pos=pos, ax=ax, arrows=True, node_size=1800,
                     font_size=8, width=1.0)
    ax.set_title(title)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)
    return target
