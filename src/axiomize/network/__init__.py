"""Network subpackage."""

from axiomize.network.epidemic import (
    build_er_graph,
    heterogeneity_factor,
    sir_on_network,
)

__all__ = ["build_er_graph", "heterogeneity_factor", "sir_on_network"]
