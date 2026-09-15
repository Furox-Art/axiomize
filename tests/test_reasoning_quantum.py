"""axiomize 2.0: quantum-inspired reasoning merged from quantum-reasoning-skill."""

from __future__ import annotations

import axiomize.reasoning.branch_controller as bc


def _metrics(**overrides):  # type: ignore[no-untyped-def]
    values = {
        "evidence": 0.8,
        "verification": 0.8,
        "independence": 0.9,
        "information_gain": 0.6,
        "contradiction": 0.1,
        "unresolved_assumptions": 0.1,
        "normalized_cost": 0.2,
        "shared_assumption_ratio": 0.0,
        "semantic_similarity_to_leader": 0.0,
    }
    values.update(overrides)
    return bc.BranchMetrics(**values)


class TestReasoningImport:
    def test_package_imports(self) -> None:
        import axiomize.reasoning as reasoning

        assert callable(reasoning.branch_score)
        assert callable(reasoning.collapse_decision)

    def test_score_penalizes_shared_assumptions(self) -> None:
        independent = _metrics(shared_assumption_ratio=0.0)
        correlated = _metrics(shared_assumption_ratio=0.8)
        assert bc.branch_score(independent) > bc.branch_score(correlated)

    def test_high_contradiction_rejects_branch(self) -> None:
        branch = bc.Branch("bad", _metrics(contradiction=0.95))
        updated = bc.classify_branch(branch)
        assert updated.state == bc.BranchState.REJECTED

    def test_material_evidence_change_revives_dormant_branch(self) -> None:
        previous = _metrics(evidence=0.30, verification=0.35, contradiction=0.50)
        current = _metrics(evidence=0.50, verification=0.35, contradiction=0.50)
        branch = bc.Branch(
            "revive",
            current,
            state=bc.BranchState.DORMANT,
            previous_metrics=previous,
        )
        assert bc.should_revive(branch)
        assert bc.update_branch_state(branch).state == bc.BranchState.ACTIVE

    def test_collapse_requires_clear_verified_leader(self) -> None:
        leader = bc.Branch(
            "leader",
            _metrics(
                evidence=1.0,
                verification=1.0,
                independence=1.0,
                information_gain=0.8,
                contradiction=0.0,
                unresolved_assumptions=0.0,
                normalized_cost=0.0,
            ),
        )
        weak = bc.Branch(
            "weak",
            _metrics(
                evidence=0.35,
                verification=0.30,
                independence=0.5,
                information_gain=0.2,
                contradiction=0.4,
                unresolved_assumptions=0.5,
                normalized_cost=0.4,
            ),
        )
        can_collapse, reason, selected = bc.collapse_decision([leader, weak])
        assert can_collapse, reason
        assert selected.branch_id == "leader"

    def test_close_competitor_blocks_collapse(self) -> None:
        first = bc.Branch(
            "a",
            _metrics(
                evidence=1.0,
                verification=1.0,
                independence=1.0,
                contradiction=0.0,
                unresolved_assumptions=0.0,
                normalized_cost=0.0,
            ),
        )
        second = bc.Branch(
            "b",
            _metrics(
                evidence=0.95,
                verification=0.95,
                independence=1.0,
                contradiction=0.0,
                unresolved_assumptions=0.0,
                normalized_cost=0.0,
            ),
        )
        can_collapse, reason, _ = bc.collapse_decision([first, second])
        assert not can_collapse
        assert "margin" in reason

    def test_uncertainty_controls_width(self) -> None:
        assert bc.recommended_width(0.10) == (2, 3)
        assert bc.recommended_width(0.40) == (4, 6)
        assert bc.recommended_width(0.90) == (6, 10)

    def test_invalid_metric_fails_fast(self) -> None:
        import pytest

        with pytest.raises(ValueError):
            bc.branch_score(_metrics(evidence=1.2))
