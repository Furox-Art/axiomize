"""Quantum-inspired multi-branch reasoning ported from quantum-reasoning-skill v0.3.1.

Reference defaults (thresholds/weights) are ported verbatim. They are
reference defaults, not validated constants — see docs/MEASUREMENT.md.
"""

from axiomize.reasoning.branch_controller import (
    DEFAULT_THRESHOLDS,
    WEIGHTS,
    Branch,
    BranchMetrics,
    BranchState,
    Thresholds,
    branch_score,
    collapse_decision,
    diversity_ratio,
    effective_independence,
    normalized_entropy,
    rank_branches,
    recommended_width,
    uncertainty_from_branches,
)

__all__ = [
    "DEFAULT_THRESHOLDS",
    "WEIGHTS",
    "Branch",
    "BranchMetrics",
    "BranchState",
    "Thresholds",
    "branch_score",
    "collapse_decision",
    "diversity_ratio",
    "effective_independence",
    "normalized_entropy",
    "rank_branches",
    "recommended_width",
    "uncertainty_from_branches",
]
