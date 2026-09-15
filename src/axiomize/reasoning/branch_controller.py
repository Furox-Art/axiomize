"""Reference branch-control logic for the Quantum Reasoning Skill.

This module is intentionally provider-agnostic. It does not generate hidden reasoning
or call an LLM. It only manages branch telemetry and makes deterministic decisions
from explicit, externally supplied measurements.

The thresholds below are reference defaults, not scientifically validated constants.
They are meant to be calibrated with benchmark evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from math import log2
from typing import Iterable, Sequence


class BranchState(str, Enum):
    ACTIVE = "active"
    DORMANT = "dormant"
    REJECTED = "rejected"


@dataclass(frozen=True)
class BranchMetrics:
    evidence: float
    verification: float
    independence: float
    information_gain: float
    contradiction: float
    unresolved_assumptions: float
    normalized_cost: float
    shared_assumption_ratio: float = 0.0
    semantic_similarity_to_leader: float = 0.0

    def validate(self) -> None:
        for name, value in self.__dict__.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {value!r}")


@dataclass(frozen=True)
class Branch:
    branch_id: str
    metrics: BranchMetrics
    state: BranchState = BranchState.ACTIVE
    previous_metrics: BranchMetrics | None = None


@dataclass(frozen=True)
class Thresholds:
    collapse_score: float = 0.78
    collapse_verification: float = 0.75
    collapse_max_contradiction: float = 0.15
    collapse_margin: float = 0.12
    unresolved_near_leader_margin: float = 0.10
    reject_contradiction: float = 0.85
    dormant_score: float = 0.35
    revive_evidence_delta: float = 0.15
    revive_verification_delta: float = 0.25
    revive_contradiction_drop: float = 0.20


DEFAULT_THRESHOLDS = Thresholds()


WEIGHTS = {
    "evidence": 0.25,
    "verification": 0.25,
    "independence": 0.15,
    "information_gain": 0.10,
    "contradiction": -0.15,
    "unresolved_assumptions": -0.05,
    "normalized_cost": -0.05,
}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def effective_independence(metrics: BranchMetrics) -> float:
    """Penalize correlated branches and near-duplicates.

    The effective independence is the declared independence reduced by the strongest
    observed correlation signal: shared assumptions or semantic similarity.
    """
    metrics.validate()
    correlation = max(
        metrics.shared_assumption_ratio,
        metrics.semantic_similarity_to_leader,
    )
    return _clamp01(metrics.independence * (1.0 - correlation))


def branch_score(metrics: BranchMetrics) -> float:
    """Return a deterministic support score in [0, 1]."""
    metrics.validate()
    values = {
        "evidence": metrics.evidence,
        "verification": metrics.verification,
        "independence": effective_independence(metrics),
        "information_gain": metrics.information_gain,
        "contradiction": metrics.contradiction,
        "unresolved_assumptions": metrics.unresolved_assumptions,
        "normalized_cost": metrics.normalized_cost,
    }
    raw = 0.15 + sum(WEIGHTS[name] * value for name, value in values.items())
    return _clamp01(raw)


def rank_branches(branches: Iterable[Branch]) -> list[Branch]:
    return sorted(
        (branch for branch in branches if branch.state != BranchState.REJECTED),
        key=lambda branch: branch_score(branch.metrics),
        reverse=True,
    )


def classify_branch(
    branch: Branch,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> Branch:
    """Move an active branch to dormant/rejected when evidence warrants it."""
    score = branch_score(branch.metrics)
    if branch.metrics.contradiction >= thresholds.reject_contradiction:
        return replace(branch, state=BranchState.REJECTED)
    if score < thresholds.dormant_score:
        return replace(branch, state=BranchState.DORMANT)
    return replace(branch, state=BranchState.ACTIVE)


def should_revive(
    branch: Branch,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> bool:
    """Return True when new evidence materially improves a dormant branch."""
    if branch.state != BranchState.DORMANT or branch.previous_metrics is None:
        return False
    current = branch.metrics
    previous = branch.previous_metrics
    current.validate()
    previous.validate()
    return any(
        (
            current.evidence - previous.evidence >= thresholds.revive_evidence_delta,
            current.verification - previous.verification
            >= thresholds.revive_verification_delta,
            previous.contradiction - current.contradiction
            >= thresholds.revive_contradiction_drop,
        )
    )


def update_branch_state(
    branch: Branch,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> Branch:
    if should_revive(branch, thresholds):
        return replace(branch, state=BranchState.ACTIVE)
    return classify_branch(branch, thresholds)


def normalized_entropy(probabilities: Sequence[float]) -> float:
    """Normalized Shannon entropy in [0, 1]."""
    if not probabilities:
        return 0.0
    if any(value < 0 for value in probabilities):
        raise ValueError("probabilities cannot contain negative values")
    total = sum(probabilities)
    if total <= 0:
        return 0.0
    normalized = [value / total for value in probabilities if value > 0]
    if len(normalized) <= 1:
        return 0.0
    entropy = -sum(value * log2(value) for value in normalized)
    return _clamp01(entropy / log2(len(normalized)))


def uncertainty_from_branches(branches: Sequence[Branch]) -> float:
    """Estimate uncertainty from the score distribution of surviving branches."""
    surviving = [
        branch_score(branch.metrics)
        for branch in branches
        if branch.state != BranchState.REJECTED
    ]
    return normalized_entropy(surviving)


def recommended_width(uncertainty: float) -> tuple[int, int]:
    """Return a reference branch-count range for the next search step."""
    if not 0.0 <= uncertainty <= 1.0:
        raise ValueError("uncertainty must be in [0, 1]")
    if uncertainty < 0.25:
        return (2, 3)
    if uncertainty < 0.55:
        return (4, 6)
    return (6, 10)


def collapse_decision(
    branches: Sequence[Branch],
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> tuple[bool, str, Branch | None]:
    """Determine whether the search can collapse to a single branch.

    Returns ``(can_collapse, reason, leader)``. Collapse is blocked when a strong,
    unresolved alternative remains close enough to the leader to matter.
    """
    ranked = rank_branches(branches)
    if not ranked:
        return (False, "no surviving branch", None)

    leader = ranked[0]
    leader_score = branch_score(leader.metrics)
    if leader_score < thresholds.collapse_score:
        return (False, "leader score below collapse threshold", leader)
    if leader.metrics.verification < thresholds.collapse_verification:
        return (False, "leader verification below collapse threshold", leader)
    if leader.metrics.contradiction > thresholds.collapse_max_contradiction:
        return (False, "leader contradiction remains too high", leader)

    if len(ranked) > 1:
        runner_up = ranked[1]
        runner_score = branch_score(runner_up.metrics)
        if leader_score - runner_score < thresholds.collapse_margin:
            return (False, "leader margin is too small", leader)
        if (
            runner_up.metrics.information_gain >= 0.60
            and leader_score - runner_score
            <= thresholds.unresolved_near_leader_margin
        ):
            return (False, "high-information alternative remains unresolved", leader)

    return (True, "collapse criteria satisfied", leader)


def diversity_ratio(
    pairwise_similarities: Sequence[float],
    duplicate_threshold: float = 0.85,
) -> float:
    """Fraction of pairwise comparisons that are materially distinct.

    Similarity values must be in [0, 1]. A pair at or above the duplicate threshold
    is treated as correlated/redundant for this diagnostic.
    """
    if not pairwise_similarities:
        return 1.0
    if not 0.0 <= duplicate_threshold <= 1.0:
        raise ValueError("duplicate_threshold must be in [0, 1]")
    for value in pairwise_similarities:
        if not 0.0 <= value <= 1.0:
            raise ValueError("similarity values must be in [0, 1]")
    distinct = sum(value < duplicate_threshold for value in pairwise_similarities)
    return distinct / len(pairwise_similarities)
