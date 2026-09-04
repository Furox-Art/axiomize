"""Adaptive workflow contract regression tests."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from axiomize.application.services import intake_service, workflow_policy_service
from axiomize.workflow.policy import RigorLevel, default_policy, recommend_rigor


def test_default_policy_guards_cost_multipliers() -> None:
    policy = default_policy()
    assert policy.permissions.allow_public_data_lookup is True
    assert policy.permissions.allow_spawn_subtasks is False
    assert policy.permissions.allow_repeat_alternative_methods is False
    assert policy.permissions.allow_extra_paid_model_calls is False
    assert policy.report.compare_multiple_models is True
    assert policy.report.rank_top_n == 3
    assert policy.report.make_plots is True
    assert policy.report.make_3d_visuals_when_useful is True


def test_rigor_aliases_remain_backward_compatible() -> None:
    assert RigorLevel.parse("basic") == RigorLevel.WEAK
    assert RigorLevel.parse("standard") == RigorLevel.MEDIUM
    assert RigorLevel.parse("research") == RigorLevel.STRONG


def test_strong_depth_is_recommended_for_multiple_escalation_signals() -> None:
    result = recommend_rigor({"mechanism_unclear": True, "high_stakes": True})
    assert result["level"] == "strong"
    assert len(result["reasons"]) >= 2


def test_quick_low_risk_run_is_weak() -> None:
    result = recommend_rigor({"quick": True})
    assert result["level"] == "weak"


def test_intake_asks_one_plain_question_by_default() -> None:
    result = intake_service({"idea": "reduce congestion in a city"})
    assert result["status"] == "NEEDS_INPUT"
    assert result["question_mode"] == "one_by_one"
    assert len(result["questions"]) == 1
    assert result["remaining_questions"] == 5


def test_intake_can_batch_questions_when_user_prefers() -> None:
    result = intake_service({
        "idea": "reduce congestion in a city",
        "question_mode": "all_at_once",
    })
    assert result["status"] == "NEEDS_INPUT"
    assert len(result["questions"]) == 5


def test_unclear_mechanism_is_not_silently_accepted() -> None:
    context = {
        "system_boundary": "urban road network",
        "goal": "reduce average travel time",
        "measurable_outcome": "mean door-to-door travel time",
        "horizon": "weekday peak hours for one year",
        "mechanism": "unknown",
    }
    result = intake_service({"idea": "reduce congestion", "context": context})
    assert result["status"] == "NEEDS_INPUT"
    assert result["questions"][0]["field"] == "mechanism"
    assert result["mechanism_uncertain"] is True


def test_ready_intake_exposes_ranked_model_workflow_and_guarded_actions() -> None:
    context = {
        "system_boundary": "urban road network",
        "goal": "reduce average travel time",
        "measurable_outcome": "mean door-to-door travel time",
        "horizon": "weekday peak hours for one year",
        "mechanism": "route choice plus demand/capacity imbalance",
    }
    result = intake_service({"idea": "reduce congestion", "context": context})
    assert result["status"] == "READY"
    assert "build_multiple_candidate_models" in result["planned_steps"]
    assert "spawn_subtask" in result["requires_user_approval_for"]
    assert "repeat_alternative_method" in result["requires_user_approval_for"]
    assert "extra_paid_model_call" in result["requires_user_approval_for"]


def test_user_can_explicitly_authorize_extra_work() -> None:
    result = workflow_policy_service({
        "permissions": {
            "allow_spawn_subtasks": True,
            "allow_repeat_alternative_methods": True,
            "allow_extra_paid_model_calls": True,
        }
    })
    permissions = result["policy"]["permissions"]
    assert permissions["allow_spawn_subtasks"] is True
    assert permissions["allow_repeat_alternative_methods"] is True
    assert permissions["allow_extra_paid_model_calls"] is True
