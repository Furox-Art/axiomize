"""Adaptive workflow contract regression tests."""

import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from axiomize.application.services import intake_service, workflow_policy_service
from axiomize.data.quality import clean_numeric_xy
from axiomize.runs.compare import compare_run_states
from axiomize.runs.state import RunState
from axiomize.visualization.plots import plot_dependency_graph, plot_sensitivity, plot_surface_3d
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


def test_data_cleaning_preserves_original_and_audits_changes() -> None:
    result = clean_numeric_xy(
        [2.0, 1.0, 1.0, 3.0, float("nan")],
        [20.0, 9.0, 11.0, 30.0, 99.0],
    )
    assert result.original_t[0] == 2.0
    assert len(result.original_t) == 5
    assert result.cleaned_t == [1.0, 2.0, 3.0]
    assert result.cleaned_y == [10.0, 20.0, 30.0]
    operations = [item["operation"] for item in result.audit]
    assert "drop_nonfinite_rows" in operations
    assert "sort_by_time" in operations
    assert "merge_duplicate_times" in operations
    assert result.material_change is True


def test_data_cleaning_retains_possible_outliers() -> None:
    result = clean_numeric_xy([0, 1, 2, 3, 4, 5, 6], [1, 1, 1, 1, 1, 1, 100])
    assert result.cleaned_y[-1] == 100.0


def test_visualization_helpers_create_files(tmp_path: Path) -> None:
    sensitivity = plot_sensitivity({"beta": 1.2, "gamma": -0.8}, tmp_path / "sensitivity.png")
    assert sensitivity.is_file() and sensitivity.stat().st_size > 0

    x = np.linspace(0, 1, 5)
    y = np.linspace(0, 1, 4)
    z = np.add.outer(y, x)
    surface = plot_surface_3d(x, y, z, tmp_path / "surface.png")
    assert surface.is_file() and surface.stat().st_size > 0

    graph = plot_dependency_graph(
        ["input", "state", "output"],
        [("input", "state"), ("state", "output")],
        tmp_path / "graph.png",
    )
    assert graph.is_file() and graph.stat().st_size > 0


def test_run_diff_explains_parameter_and_tool_version_changes() -> None:
    before = RunState(parameters={"beta": 0.3}, solver_settings={"rtol": 1e-6}, results={"y": 1.0})
    after = RunState(parameters={"beta": 0.4}, solver_settings={"rtol": 1e-6}, results={"y": 1.5})
    diff = compare_run_states(
        before,
        after,
        before_manifest={"tool_versions": {"scipy": "1.10.0"}},
        after_manifest={"tool_versions": {"scipy": "1.11.0"}},
    )
    assert diff["same_input_hash"] is False
    assert "parameters" in diff["differences"]
    assert "tool_versions" in diff["differences"]
    assert "model parameters changed" in diff["likely_reasons"]
    assert "software/tool versions changed" in diff["likely_reasons"]
