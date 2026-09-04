"""User-controlled policy for the adaptive Axiomize workflow.

This module encodes product behavior independently of any model provider. The
scientific engine can therefore enforce honesty, reproducibility and spending
boundaries even when different agents/providers drive the workflow.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class RigorLevel(str, Enum):
    """User-facing depth labels with backwards-compatible aliases."""

    WEAK = "weak"
    MEDIUM = "medium"
    STRONG = "strong"

    @classmethod
    def parse(cls, value: str | None) -> "RigorLevel | None":
        if value is None:
            return None
        aliases = {
            "weak": cls.WEAK,
            "basic": cls.WEAK,
            "medium": cls.MEDIUM,
            "standard": cls.MEDIUM,
            "strong": cls.STRONG,
            "research": cls.STRONG,
        }
        try:
            return aliases[value.strip().lower()]
        except KeyError as exc:
            raise ValueError(
                "rigor must be weak/medium/strong "
                "(basic/standard/research are accepted aliases)"
            ) from exc


class QuestionMode(str, Enum):
    ONE_BY_ONE = "one_by_one"
    ALL_AT_ONCE = "all_at_once"
    ADAPTIVE = "adaptive"

    @classmethod
    def parse(cls, value: str | None) -> "QuestionMode":
        if value is None:
            return cls.ADAPTIVE
        aliases = {
            "one_by_one": cls.ONE_BY_ONE,
            "one-by-one": cls.ONE_BY_ONE,
            "single": cls.ONE_BY_ONE,
            "all_at_once": cls.ALL_AT_ONCE,
            "all-at-once": cls.ALL_AT_ONCE,
            "batch": cls.ALL_AT_ONCE,
            "adaptive": cls.ADAPTIVE,
        }
        try:
            return aliases[value.strip().lower()]
        except KeyError as exc:
            raise ValueError("question_mode must be one_by_one, all_at_once, or adaptive") from exc


class ConfidenceLabel(str, Enum):
    CERTAIN = "certain"
    STRONG_PROBABILITY = "strong_probability"
    MEDIUM_CONFIDENCE = "medium_confidence"
    LOW_CONFIDENCE = "low_confidence"


@dataclass(frozen=True)
class ExecutionPermissions:
    """Bound actions that can unexpectedly increase cost or alter a model.

    The defaults intentionally allow bounded local deterministic work while
    requiring consent for multiplicative compute, new mechanism discovery,
    constraint-driven rebuilds, or schema migration.
    """

    allow_public_data_lookup: bool = True
    allow_spawn_subtasks: bool = False
    allow_repeat_alternative_methods: bool = False
    allow_extra_paid_model_calls: bool = False
    allow_heavy_compute: bool = False
    allow_constraint_rebuild: bool = False
    allow_model_discovery: bool = False
    allow_experiment_design: bool = False
    allow_ir_migration: bool = False
    allow_visualization: bool = True
    allow_3d_visualization: bool = True

    def requires_approval(self, action: str) -> bool:
        guarded = {
            "spawn_subtask": self.allow_spawn_subtasks,
            "repeat_alternative_method": self.allow_repeat_alternative_methods,
            "extra_paid_model_call": self.allow_extra_paid_model_calls,
            "heavy_compute": self.allow_heavy_compute,
            "constraint_rebuild": self.allow_constraint_rebuild,
            "model_discovery": self.allow_model_discovery,
            "experiment_design": self.allow_experiment_design,
            "ir_migration": self.allow_ir_migration,
        }
        if action not in guarded:
            return False
        return not guarded[action]


@dataclass(frozen=True)
class ReportRequirements:
    """Behavior required for substantive modeling runs."""

    compare_multiple_models: bool = True
    rank_top_n: int = 3
    explain_rank_reasons: bool = True
    explain_when_each_model_is_best: bool = True
    explain_model_choice: bool = True
    self_check_for_errors: bool = True
    disclose_uncertainty: bool = True
    label_confidence: bool = True
    list_failure_risks: bool = True
    state_validity_domain: bool = True

    identify_required_data: bool = True
    prioritize_missing_data: bool = True
    check_source_reliability: bool = True
    compare_conflicting_sources: bool = True
    warn_on_stale_sources: bool = True

    clean_bad_data_before_fit: bool = True
    audit_data_cleaning: bool = True
    preserve_original_data: bool = True
    compare_original_vs_cleaned: bool = True
    highlight_cleaning_sensitive_results: bool = True

    rank_sensitive_variables: bool = True
    show_sensitivity_scenarios: bool = True
    make_plots: bool = True
    make_3d_visuals_when_useful: bool = True
    make_dependency_graphs: bool = True

    propose_real_world_test: bool = True
    simulation_first_when_test_is_costly_or_risky: bool = True
    produce_hypothesis_test_plan: bool = True
    revise_failed_hypotheses: bool = True
    rank_hypotheses: int = 3
    state_hypothesis_evidence_needs: bool = True
    reject_weak_hypotheses_with_reason: bool = True

    explain_method_disagreement: bool = True
    reproducible_runs: bool = True
    explain_rerun_differences: bool = True
    layered_output: bool = True
    user_controls_detail: bool = True
    offer_stronger_rerun: bool = True

    # General model-engine invariants.
    explicit_model_ir: bool = True
    check_units_and_dimensions: bool = True
    show_scientific_constraint_checks: bool = True
    show_solver_selection: bool = True
    diagnose_solver_failures: bool = True
    check_identifiability_before_interpreting_fit: bool = True
    penalize_unnecessary_model_complexity: bool = True
    residual_and_out_of_sample_diagnostics: bool = True
    analyze_validity_region: bool = True
    analyze_stability_when_applicable: bool = True
    propose_nondimensionalization_when_ill_conditioned: bool = True
    separate_aleatoric_and_epistemic_uncertainty: bool = True
    discriminate_competing_mechanisms: bool = True
    quantify_experiment_information_gain: bool = True
    validate_discovered_equations_against_science: bool = True
    compare_discovered_models_with_domain_theory: bool = True
    prohibit_causal_claims_from_fit_alone: bool = True
    show_compute_estimate_before_heavy_work: bool = True
    provenance_audit_trail: bool = True
    portable_model_export: bool = True
    explicit_stopping_criteria: bool = True
    versioned_backward_compatible_ir: bool = True
    never_silently_migrate_or_repair: bool = True


@dataclass(frozen=True)
class WorkflowPolicy:
    question_mode: QuestionMode = QuestionMode.ADAPTIVE
    auto_select_rigor: bool = True
    show_rigor_recommendation: bool = True
    permissions: ExecutionPermissions = field(default_factory=ExecutionPermissions)
    report: ReportRequirements = field(default_factory=ReportRequirements)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["question_mode"] = self.question_mode.value
        return payload


def default_policy(*, question_mode: str | None = None,
                   permissions: dict[str, Any] | None = None) -> WorkflowPolicy:
    mode = QuestionMode.parse(question_mode)
    perms = ExecutionPermissions(**(permissions or {}))
    return WorkflowPolicy(question_mode=mode, permissions=perms)


def recommend_rigor(signals: dict[str, Any] | None = None) -> dict[str, Any]:
    """Recommend weak/medium/strong from explicit, machine-readable signals."""
    signals = dict(signals or {})
    reasons: list[str] = []

    if bool(signals.get("research")) or bool(signals.get("publication")):
        return {
            "level": RigorLevel.STRONG.value,
            "reasons": ["research/publication-grade output requested"],
        }

    strong_flags = {
        "high_stakes": "high-stakes consequence",
        "multi_domain": "multiple scientific domains interact",
        "mechanism_unclear": "core mechanism is uncertain",
        "model_conflict": "candidate models disagree",
        "high_sensitivity": "result is highly parameter-sensitive",
        "causal_claim": "causal claim requires stronger validation",
        "real_world_experiment": "real-world experiment needs stronger validation",
        "pde_or_dae": "PDE/DAE structure usually needs stronger numerical checks",
        "model_discovery": "data-driven equation discovery needs strong falsification",
    }
    score = 0
    for key, reason in strong_flags.items():
        if bool(signals.get(key)):
            score += 1
            reasons.append(reason)

    if score >= 2:
        return {"level": RigorLevel.STRONG.value, "reasons": reasons}

    if bool(signals.get("quick")) and score == 0:
        return {
            "level": RigorLevel.WEAK.value,
            "reasons": ["quick/lightweight run requested and no escalation signal present"],
        }

    if reasons:
        reasons.append("one escalation signal is present; medium keeps cost bounded while adding checks")
    else:
        reasons.append("default balanced depth")
    return {"level": RigorLevel.MEDIUM.value, "reasons": reasons}
