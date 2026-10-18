"""Offline provider never invents measurements; workflow decisions require declared consent."""

from __future__ import annotations

import pytest

from axiomize.providers.echo import EchoProvider
from axiomize.workflow.policy import (
    ExecutionPermissions,
    QuestionMode,
    RigorLevel,
    default_policy,
    recommend_rigor,
)


def test_offline_provider_identifies_its_limited_capabilities_without_external_claims():
    provider = EchoProvider()
    assert provider.name == "echo"
    assert provider.supports_tools is False
    assert provider.supports_structured_output is True
    assert provider.context_limit == 1_000_000
    assert provider.health_check() is True
    assert provider.generate("actual observed input") == "echo: actual observed input"


def test_offline_schema_response_preserves_unknown_observations_as_null():
    provider = EchoProvider()
    out = provider.generate_structured(
        "please supply experimental observations",
        {
            "properties": {"count": {"type": "number"}, "record": {"type": "string"}},
            "required": ["record", "measurement_not_provided"],
        },
    )
    assert out == {"count": 0.0, "record": None, "measurement_not_provided": None}


def test_offline_provider_missing_schema_fields_remain_explicitly_absent():
    assert EchoProvider().generate_structured("sample", {}) == {}
    assert EchoProvider().generate_structured("sample", {"required": ["unknown"]}) == {"unknown": None}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("weak", RigorLevel.WEAK),
        (" basic ", RigorLevel.WEAK),
        ("medium", RigorLevel.MEDIUM),
        ("standard", RigorLevel.MEDIUM),
        ("strong", RigorLevel.STRONG),
        (" RESEARCH ", RigorLevel.STRONG),
    ],
)
def test_user_selected_rigor_level_preserves_known_explicit_alias(source, expected):
    assert RigorLevel.parse(source) == expected


def test_missing_explicit_rigor_is_not_assumed_to_be_high_certainty():
    assert RigorLevel.parse(None) is None


def test_unknown_rigor_level_is_rejected_not_coerced_to_favorable_label():
    with pytest.raises(ValueError, match="rigor must be"):
        RigorLevel.parse("absolutely proven")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (None, QuestionMode.ADAPTIVE),
        ("single", QuestionMode.ONE_BY_ONE),
        (" one-by-one ", QuestionMode.ONE_BY_ONE),
        ("batch", QuestionMode.ALL_AT_ONCE),
        ("all-at-once", QuestionMode.ALL_AT_ONCE),
        ("adaptive", QuestionMode.ADAPTIVE),
    ],
)
def test_question_display_mode_uses_only_explicit_approved_aliases(source, expected):
    assert QuestionMode.parse(source) == expected


def test_unknown_question_mode_is_a_configuration_error_not_a_guess():
    with pytest.raises(ValueError, match="question_mode must be"):
        QuestionMode.parse("unknown-stage")


@pytest.mark.parametrize(
    "action",
    [
        "spawn_subtask",
        "repeat_alternative_method",
        "extra_paid_model_call",
        "heavy_compute",
        "constraint_rebuild",
        "model_discovery",
        "experiment_design",
        "ir_migration",
    ],
)
def test_all_expensive_or_model_changing_actions_need_user_consent_by_default(action):
    assert ExecutionPermissions().requires_approval(action) is True


def test_approved_heavy_computation_is_not_confused_with_unapproved_model_discovery():
    p = ExecutionPermissions(allow_heavy_compute=True)
    assert p.requires_approval("heavy_compute") is False
    assert p.requires_approval("model_discovery") is True
    assert p.requires_approval("non_guarded_read_only_action") is False


def test_default_policy_honors_explicit_batch_mode_and_visual_consent():
    policy = default_policy(
        question_mode="all-at-once",
        permissions={"allow_heavy_compute": True, "allow_visualization": False},
    )
    serialized = policy.to_dict()
    assert serialized["question_mode"] == "all_at_once"
    assert serialized["permissions"]["allow_heavy_compute"] is True
    assert serialized["permissions"]["allow_visualization"] is False
    assert serialized["report"]["reproducible_runs"] is True


@pytest.mark.parametrize(
    "flags",
    [
        {"research": True},
        {"publication": True},
        {"causal_claim": True, "high_sensitivity": True},
        {"model_discovery": True, "pde_or_dae": True},
    ],
)
def test_explicit_publication_or_multiple_risk_signals_escalate_rigor(flags):
    out = recommend_rigor(flags)
    assert out["level"] == "strong"
    assert out["reasons"]


def test_quick_mode_only_weakens_rigor_when_no_risk_flag_is_present():
    assert recommend_rigor({"quick": True})["level"] == "weak"
    mixed = recommend_rigor({"quick": True, "causal_claim": True})
    assert mixed["level"] == "medium"


def test_absent_risk_flags_recommend_balanced_depth_without_false_research_claim():
    out = recommend_rigor({})
    assert out == {"level": "medium", "reasons": ["default balanced depth"]}


def test_a_single_stronger_mechanism_flag_is_reported_without_fabricated_extra_risk():
    out = recommend_rigor({"mechanism_unclear": True})
    assert out["level"] == "medium"
    assert len(out["reasons"]) == 2
