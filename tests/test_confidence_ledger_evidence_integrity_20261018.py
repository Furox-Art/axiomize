"""Independent evidence-status and weighted confidence regression contracts.

The tests intentionally exercise conflicting, missing and unavailable evidence
as distinct scientific outcomes. They never invent unprovided measurements.
"""
from __future__ import annotations

import math

import pytest

from axiomize.validation import ledger as L
from axiomize.validation.status import ValidationStatus as S


@pytest.mark.parametrize("raw,expected", [
    ("symbolic", "symbolic"),
    ("CROSSVALIDATION", "cross_validation"),
    ("Cross-Validation", "cross_validation"),
    ("CROSS_VALIDATION", "cross_validation"),
    ("XVAL", "cross_validation"),
    ("numerical", "numerical"),
])
def test_evidence_kind_alias_has_single_normalized_identity(raw, expected):
    assert L._normalize_kind(raw) == expected


def test_unknown_evidence_kind_is_rejected():
    with pytest.raises(ValueError, match="bilinmeyen kanit"):
        L._normalize_kind("made_up_evidence")


@pytest.mark.parametrize("raw,status", [
    (None, None), (S.PASS, S.PASS), (" PASS ", S.PASS),
    ("warning", S.WARNING), ("tool_unavailable", S.TOOL_UNAVAILABLE),
])
def test_status_coercion_is_exact_and_auditable(raw, status):
    assert L._coerce_status(raw) == status


def test_unknown_string_status_does_not_turn_into_pass():
    with pytest.raises(ValueError, match="bilinmeyen status"):
        L._coerce_status("unknown")


def test_nonstatus_nonstrings_are_not_silently_accepted():
    assert L._coerce_status(123) is None
    with pytest.raises(ValueError, match="status ValidationStatus olmali"):
        L._normalize_evidence("symbolic", {"status": 123})


@pytest.mark.parametrize("value,status,detail", [
    (None, S.UNVERIFIED, "girdi verilmedi"),
    (S.PASS, S.PASS, None),
    ("FAIL", S.FAIL, None),
    ({"note": "unverified source"}, S.UNVERIFIED, {"note": "unverified source"}),
    ({"status": "PASS", "detail": "direct proof"}, S.PASS, "direct proof"),
])
def test_evidence_normalization_never_invents_status(value, status, detail):
    assert L._normalize_evidence("symbolic", value) == (status, detail)


class UnjudgedReport:
    def __init__(self, contents, error=False):
        self.contents = contents
        self.error = error

    def to_dict(self):
        if self.error:
            raise RuntimeError("external report failed")
        return self.contents


@pytest.mark.parametrize("value,marker", [
    (UnjudgedReport({"value": 42}), "ham rapor"),
    (UnjudgedReport({}), "bos rapor"),
    (UnjudgedReport({"value": 0}), "bos rapor"),
    (UnjudgedReport(None), "bos rapor"),
    (UnjudgedReport({}, error=True), "bos rapor"),
])
def test_unjudged_third_party_reports_never_become_proven_facts(value, marker):
    status, detail = L._normalize_evidence("uncertainty", value)
    assert status is S.UNVERIFIED
    assert marker in detail


def test_opaque_unsupported_input_is_rejected_not_coerced():
    with pytest.raises(TypeError, match="beklenen girdi"):
        L._normalize_evidence("numerical", 123)


@pytest.mark.parametrize("items,result", [
    ({}, L.DEFAULT_WEIGHTS),
    ({"XVAL": 0.4}, {**L.DEFAULT_WEIGHTS, "cross_validation": 0.4}),
    ({"numerical": 0.0}, {**L.DEFAULT_WEIGHTS, "numerical": 0.0}),
])
def test_weight_overrides_only_replace_stated_evidence_kind(items, result):
    assert L._resolve_weights(items) == result


def test_negative_or_unknown_weight_is_an_error():
    with pytest.raises(ValueError, match="negatif"):
        L._resolve_weights({"symbolic": -0.5})
    with pytest.raises(ValueError, match="bilinmeyen kanit"):
        L._resolve_weights({"unregistered": 1.0})


@pytest.mark.parametrize("status,expected", [
    (S.PASS, S.PASS),
    (S.FAIL, S.FAIL),
    (S.CONFLICT, S.CONFLICT),
    (S.WARNING, S.WARNING),
    (S.INCONCLUSIVE, S.WARNING),
    (S.TOOL_UNAVAILABLE, S.TOOL_UNAVAILABLE),
    (S.UNVERIFIED, S.UNVERIFIED),
])
def test_all_evidence_with_same_status_produces_correct_overall(status,expected):
    actual=L._overall_status({kind:status for kind in L.EVIDENCE_KINDS})
    assert actual is expected


def test_failure_beats_conflict_and_pass_for_overall_status():
    evidence={k:S.PASS for k in L.EVIDENCE_KINDS}
    evidence["symbolic"]=S.FAIL
    evidence["numerical"]=S.CONFLICT
    assert L._overall_status(evidence) is S.FAIL


def test_conflict_beats_warning_but_not_failure():
    evidence={k:S.PASS for k in L.EVIDENCE_KINDS}
    evidence["symbolic"]=S.CONFLICT
    evidence["numerical"]=S.WARNING
    assert L._overall_status(evidence) is S.CONFLICT


def test_mixed_unavailable_and_unverified_are_not_a_pass():
    evidence={k:S.TOOL_UNAVAILABLE for k in L.EVIDENCE_KINDS}
    evidence["uncertainty"]=S.UNVERIFIED
    assert L._overall_status(evidence) is S.UNVERIFIED


def test_complete_high_confidence_requires_all_five_accepted_evidence_kinds():
    result=L.build_ledger(**{k:S.PASS for k in L.EVIDENCE_KINDS})
    assert result.overall_status is S.PASS
    assert result.confidence==pytest.approx(1.0)
    assert result.scored_weight==pytest.approx(1.0)
    assert result.total_weight==pytest.approx(1.0)
    assert {row["status"] for row in result.to_dict()["entries"].values()}=={"PASS"}


def test_unobserved_evidence_is_zero_not_an_invented_score():
    result=L.build_ledger()
    assert result.overall_status is S.UNVERIFIED
    assert result.confidence==0.0
    assert result.scored_weight==0.0
    assert result.total_weight==pytest.approx(1.0)
    assert all(entry.score is None for entry in result.entries.values())


def test_weight_denominator_uses_only_judged_evidence():
    # The remaining three unverified inputs must not dilute or invent a score.
    result=L.build_ledger(symbolic=S.PASS, numerical=S.FAIL)
    assert result.scored_weight==pytest.approx(0.5)
    assert result.confidence==pytest.approx(0.5)
    assert result.overall_status is S.FAIL
    assert result.entries["uncertainty"].score is None


@pytest.mark.parametrize("status,expected", [
    (S.PASS,1.0),(S.WARNING,0.6),(S.INCONCLUSIVE,0.5),
    (S.CONFLICT,0.3),(S.FAIL,0.0),
])
def test_single_judged_evidence_has_exact_confidence_mapping(status,expected):
    result=L.build_ledger(symbolic=status)
    assert result.confidence==pytest.approx(expected)
    assert result.scored_weight==pytest.approx(L.DEFAULT_WEIGHTS["symbolic"])


def test_alias_is_resolved_once_into_original_evidence_slot():
    result=L.build_ledger(XVAL={"status":"PASS","detail":"held-out validation"})
    assert result.entries["cross_validation"].status is S.PASS
    assert result.entries["cross_validation"].detail=="held-out validation"


def test_duplicate_explicit_and_aliased_evidence_is_refused():
    with pytest.raises(ValueError, match="iki kez"):
        L.build_ledger(cross_validation=S.PASS, XVAL=S.FAIL)


def test_unknown_alias_is_not_ignored():
    with pytest.raises(ValueError, match="bilinmeyen kanit"):
        L.build_ledger(unknown_kind=S.PASS)


def test_explicit_zero_weight_cannot_silently_affect_confidence():
    result=L.build_ledger(symbolic=S.FAIL, numerical=S.PASS, weights={"symbolic":0.0})
    assert result.confidence==pytest.approx(1.0)
    assert result.scored_weight==pytest.approx(L.DEFAULT_WEIGHTS["numerical"])
    assert math.isfinite(result.confidence)
