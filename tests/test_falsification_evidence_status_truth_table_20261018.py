"""Every falsification outcome is evidence-scoped; missing tests never pass."""
from __future__ import annotations

import pytest

from axiomize.falsification.engine import Falsifier, evaluate_falsifiers
from axiomize.validation.status import ValidationStatus as S


@pytest.mark.parametrize("direction,observed,expected_trigger,expected_status", [
    ("above", 11.0, True, S.FAIL),
    ("above", 9.0, False, S.PASS),
    ("above", 10.0, False, S.PASS),
    ("below", 9.0, True, S.FAIL),
    ("below", 11.0, False, S.PASS),
    ("below", 10.0, False, S.PASS),
])
def test_actual_observation_is_compared_to_declared_boundary(direction, observed, expected_trigger, expected_status):
    falsifier = Falsifier(name="empirical-rate", observable="rate", threshold=10.0, direction=direction)
    outcome = falsifier.evaluate(observed)
    assert outcome["triggered"] is expected_trigger
    assert outcome["status"] is expected_status
    assert outcome["observed"] == observed


def test_no_falsifiers_does_not_fabricate_a_verified_model():
    result = evaluate_falsifiers([], {})
    assert result["model_status"] is S.UNVERIFIED
    assert result["results"] == []


def test_only_unmeasured_falsifiers_are_explicitly_unverified():
    actual = evaluate_falsifiers(
        [Falsifier("needed", "missing-signal", 2.0)],
        {},
    )
    assert actual["model_status"] is S.UNVERIFIED
    assert actual["untested"] == ["missing-signal"]
    assert actual["results"] == []


def test_partial_observation_cannot_silently_pass_unverified_criteria():
    actual = evaluate_falsifiers([
        Falsifier("checked", "a", 5.0, "above"),
        Falsifier("pending", "b", 5.0, "below"),
    ], {"a": 4.0})
    assert actual["model_status"] is S.UNVERIFIED
    assert len(actual["results"]) == 1
    assert actual["results"][0]["status"] is S.PASS
    assert actual["untested"] == ["b"]


def test_direct_failure_takes_priority_over_missing_criteria():
    actual = evaluate_falsifiers([
        Falsifier("rejected", "a", 5.0, "above"),
        Falsifier("pending", "b", 5.0, "below"),
    ], {"a": 6.0})
    assert actual["model_status"] is S.FAIL
    assert actual["results"][0]["status"] is S.FAIL
    assert actual["untested"] == ["b"]


def test_full_measured_nonviolation_is_a_proper_pass():
    actual = evaluate_falsifiers([
        Falsifier("one", "a", 5.0, "above"),
        Falsifier("two", "b", 5.0, "below"),
    ], {"a": 4.0, "b": 6.0})
    assert actual["model_status"] is S.PASS
    assert all(entry["status"] is S.PASS for entry in actual["results"])
    assert actual["untested"] == []
