"""User-consent intake and actual ScientificTool availability contracts."""
from __future__ import annotations

import pytest

from axiomize.tools.base import ScientificTool, ToolMetadata
from axiomize.workflow import intake
from axiomize.workflow.policy import QuestionMode


def complete_context():
    return {
        "system_boundary": "two-compartment physical system",
        "goal": "predict observed decay",
        "measurable_outcome": "concentration",
        "horizon": "one hour",
        "mechanism": "first-order exchange",
    }


class WorkingBackend(ScientificTool):
    name = "real-lifecycle"
    capabilities = ["bounded-numeric"]

    @classmethod
    def _probe_version(cls):
        return "1.0.0"

    def validate_input(self, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("x"), (int, float)):
            raise ValueError("numeric observation required")

    def execute(self, payload):
        self.validate_input(payload)
        result = {"observed_double": 2 * payload["x"]}
        self.validate_output(result)
        return result


class UnavailableBackend(WorkingBackend):
    name = "missing-scientific-library"

    @classmethod
    def _probe_version(cls):
        raise OSError("native scientific library unavailable")


@pytest.mark.parametrize("payload,error", [
    ({}, "idea"),
    ({"idea": ""}, "idea"),
    ({"idea": "   "}, "idea"),
    ({"idea": "effect", "context": []}, "context"),
    ({"idea": "effect", "permissions": []}, "permissions"),
    ({"idea": "effect", "question_mode": "unsupported"}, "question_mode"),
])
def test_workflow_intake_rejects_unjustified_missing_fields(payload, error):
    with pytest.raises(ValueError, match=error):
        intake.build_intake_response(payload)


@pytest.mark.parametrize("missing_value", [None, "", "  ", "unsure", "UNKNOWN", "bilmiyorum", "not sure"])
def test_missing_mechanism_is_an_explicit_question_not_an_invented_axiom(missing_value):
    context = complete_context()
    context["mechanism"] = missing_value
    out = intake.build_intake_response({"idea": "decay", "context": context})
    assert out["status"] == "NEEDS_INPUT"
    assert out["questions"][0]["field"] == "mechanism"
    assert out["mechanism_uncertain"] is True


def test_adaptive_question_mode_uses_one_question_and_explicit_count():
    out = intake.build_intake_response({"idea": "experiment"})
    assert out["status"] == "NEEDS_INPUT"
    assert out["question_mode"] == "one_by_one"
    assert out["remaining_questions"] == 5
    assert [q["field"] for q in out["questions"]] == ["system_boundary"]


@pytest.mark.parametrize("mode", ["all_at_once", "batch"])
def test_all_question_mode_keeps_all_unknown_observables(mode):
    out = intake.build_intake_response({"idea": "experiment", "question_mode": mode})
    assert out["question_mode"] == "all_at_once"
    assert {q["field"] for q in out["questions"]} == set(complete_context())


def test_adaptive_preference_may_select_batch_without_inventing_answers():
    out = intake.build_intake_response({
        "idea": "experimental model", "preferred_question_mode": "batch"
    })
    assert out["question_mode"] == "all_at_once"
    assert len(out["questions"]) == 5


def test_explicit_adaptive_preference_still_defaults_to_one_at_a_time():
    out = intake.build_intake_response({
        "idea": "experimental model", "preferred_question_mode": "adaptive"
    })
    assert out["question_mode"] == QuestionMode.ONE_BY_ONE.value
    assert len(out["questions"]) == 1


def test_complete_user_supplied_mechanism_allows_work_without_consent_assumption():
    out = intake.build_intake_response({
        "idea": "physical decay", "context": complete_context(),
        "rigor": "research", "signals": {"research": True},
    })
    assert out["status"] == "READY"
    assert "mechanism_uncertain" not in out
    assert out["effective_rigor"] == "strong"
    assert out["remaining_questions"] == 0
    assert out["requires_user_approval_for"] == [
        "spawn_subtask", "repeat_alternative_method", "extra_paid_model_call"
    ]
    assert "record_reproducible_run" in out["planned_steps"]


def test_explicit_action_permission_is_not_swallowed_or_inverted():
    out = intake.build_intake_response({
        "idea": "physical decay", "context": complete_context(),
        "permissions": {
            "allow_spawn_subtasks": True,
            "allow_extra_paid_model_calls": True,
        },
    })
    assert out["status"] == "READY"
    assert out["requires_user_approval_for"] == ["repeat_alternative_method"]


def test_real_backend_probe_includes_version_and_required_capabilities():
    tool = WorkingBackend()
    meta = tool.metadata()
    assert isinstance(meta, ToolMetadata)
    assert meta.available is True
    assert meta.version == "1.0.0"
    assert meta.capabilities == ["bounded-numeric"]
    assert tool.execute({"x": 0.125}) == {"observed_double": 0.25}


def test_backend_probe_failure_refuses_false_available_state():
    tool = UnavailableBackend()
    meta = tool.metadata()
    assert meta.available is False
    assert meta.reason == "native scientific library unavailable"
    assert meta.capabilities == ["bounded-numeric"]


def test_base_class_requires_real_implementation_and_cannot_be_instantiated():
    with pytest.raises(TypeError, match="abstract"):
        ScientificTool()


def test_backend_output_must_be_actual_json_object():
    tool = WorkingBackend()
    with pytest.raises(TypeError, match="result must be a dict"):
        tool.validate_output([{"fabricated": "success"}])
    with pytest.raises(ValueError, match="numeric observation required"):
        tool.execute({"x": None})
