"""Adaptive intake for vague scientific ideas.

The intake layer decides what is still missing before model construction.  It
never silently invents the system boundary, goal or core mechanism.  Optional
missing information may later be handled as an explicit assumption with a
confidence warning by the modeling layer.
"""

from __future__ import annotations

from typing import Any

from axiomize.workflow.policy import QuestionMode, RigorLevel, default_policy, recommend_rigor


_QUESTIONS: list[tuple[str, str]] = [
    ("system_boundary", "What exactly are we modeling, and what is outside the system?"),
    ("goal", "What should the model predict, explain, optimize, or control?"),
    ("measurable_outcome", "What could we measure to tell whether it is working?"),
    ("horizon", "Over what time period or spatial scale should the model apply?"),
    ("mechanism", "What do you think causes the main effect? If you are unsure, say what part is unclear."),
]

_UNCERTAIN_MARKERS = {
    "unknown", "unsure", "unclear", "not sure", "don't know", "do not know",
    "belirsiz", "bilmiyorum", "emin değilim", "emin degilim",
}


def _has_answer(context: dict[str, Any], key: str) -> bool:
    value = context.get(key)
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip().lower()
        if not text or text in _UNCERTAIN_MARKERS:
            return False
    return True


def _missing(context: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"field": key, "question": question}
        for key, question in _QUESTIONS
        if not _has_answer(context, key)
    ]


def build_intake_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the next clarification step and deterministic workflow policy."""
    idea = str(payload.get("idea", "")).strip()
    if not idea:
        raise ValueError("idea must be a non-empty string")

    context = payload.get("context", {})
    if not isinstance(context, dict):
        raise ValueError("context must be an object")

    permissions = payload.get("permissions")
    if permissions is not None and not isinstance(permissions, dict):
        raise ValueError("permissions must be an object")

    policy = default_policy(
        question_mode=payload.get("question_mode"),
        permissions=permissions,
    )
    recommendation = recommend_rigor(payload.get("signals"))
    requested = RigorLevel.parse(payload.get("rigor"))
    effective = requested or RigorLevel(recommendation["level"])

    missing = _missing(context)
    mode = policy.question_mode
    # Adaptive means the engine honors an explicit per-request preference; when
    # none is supplied, one short question at a time is the least overwhelming
    # and cheapest interaction pattern.
    if mode == QuestionMode.ADAPTIVE:
        preferred = str(payload.get("preferred_question_mode", "one_by_one"))
        mode = QuestionMode.parse(preferred)
        if mode == QuestionMode.ADAPTIVE:
            mode = QuestionMode.ONE_BY_ONE

    if missing:
        questions = missing[:1] if mode == QuestionMode.ONE_BY_ONE else missing
        return {
            "status": "NEEDS_INPUT",
            "idea": idea,
            "questions": questions,
            "remaining_questions": len(missing),
            "question_mode": mode.value,
            "rigor_recommendation": recommendation,
            "effective_rigor": effective.value,
            "policy": policy.to_dict(),
            "mechanism_uncertain": any(q["field"] == "mechanism" for q in missing),
        }

    planned_steps = [
        "build_multiple_candidate_models",
        "compare_when_each_model_is_best",
        "rank_top_models_with_reasons",
        "fit_and_validate_when_data_exist",
        "quantify_uncertainty_and_confidence",
        "check_falsifiers_and_validity_domain",
        "rank_sensitive_variables_and_scenarios",
        "visualize_results_and_dependencies",
        "produce_hypothesis_and_test_plan_when_applicable",
        "record_reproducible_run",
    ]
    guarded = [
        action
        for action in (
            "spawn_subtask",
            "repeat_alternative_method",
            "extra_paid_model_call",
        )
        if policy.permissions.requires_approval(action)
    ]
    return {
        "status": "READY",
        "idea": idea,
        "questions": [],
        "remaining_questions": 0,
        "question_mode": mode.value,
        "rigor_recommendation": recommendation,
        "effective_rigor": effective.value,
        "policy": policy.to_dict(),
        "planned_steps": planned_steps,
        "requires_user_approval_for": guarded,
    }
