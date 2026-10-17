"""Evidence weighting must never promote missing or invalid claims to PASS."""

from __future__ import annotations

import math

import pytest

from axiomize.validation.ledger import EVIDENCE_KINDS, build_ledger
from axiomize.validation.status import ValidationStatus


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["PASS"] * 5, ValidationStatus.PASS),
        (["FAIL", "PASS", "PASS", "PASS", "PASS"], ValidationStatus.FAIL),
        (["CONFLICT", "PASS", "PASS", "PASS", "PASS"], ValidationStatus.CONFLICT),
        (["WARNING", "PASS", "PASS", "PASS", "PASS"], ValidationStatus.WARNING),
        (["INCONCLUSIVE", "PASS", "PASS", "PASS", "PASS"], ValidationStatus.WARNING),
        (["UNVERIFIED"] * 5, ValidationStatus.UNVERIFIED),
        (["TOOL_UNAVAILABLE"] * 5, ValidationStatus.TOOL_UNAVAILABLE),
        (["TOOL_UNAVAILABLE", "PASS", "PASS", "PASS", "PASS"], ValidationStatus.UNVERIFIED),
    ],
)
def test_status_combination_does_not_promote_incomplete_evidence(statuses, expected):
    record = dict(zip(EVIDENCE_KINDS, statuses, strict=True))
    report = build_ledger(**record)
    assert report.overall_status is expected


@pytest.mark.parametrize(
    ("status", "score"), [("PASS", 1.0), ("WARNING", 0.6), ("INCONCLUSIVE", 0.5), ("CONFLICT", 0.3), ("FAIL", 0.0)]
)
def test_single_evidence_score_renormalizes_only_assessed_evidence(status, score):
    report = build_ledger(symbolic=status)
    assert report.confidence == pytest.approx(score)
    assert report.scored_weight == pytest.approx(0.25)
    assert report.total_weight == pytest.approx(1.0)
    assert report.entries["numerical"].score is None


def test_mix_of_pass_fail_and_unavailable_uses_actual_scored_weights():
    report = build_ledger(
        symbolic={"status": "PASS", "detail": {"exact": True}},
        numerical=ValidationStatus.FAIL,
        cross_validation="TOOL_UNAVAILABLE",
        falsification="UNVERIFIED",
        uncertainty=None,
    )
    assert report.confidence == pytest.approx(0.5)
    assert report.scored_weight == pytest.approx(0.5)
    assert report.entries["symbolic"].detail == {"exact": True}
    assert report.overall_status is ValidationStatus.FAIL
    assert report.to_dict()["entries"]["symbolic"]["status"] == "PASS"


@pytest.mark.parametrize(
    ("weights", "message"),
    [
        ({"numerical": float("nan")}, "sonlu"),
        ({"numerical": float("inf")}, "sonlu"),
        ({"numerical": -float("inf")}, "sonlu"),
        ({"numerical": -0.01}, "negatif"),
        ({"numerical": True}, "sonlu"),
        ({"numerical": "not-a-number"}, "sonlu"),
        ({"unknown": 1.0}, "bilinmeyen kanit turu"),
    ],
)
def test_bad_weights_never_silently_corrupt_confidence(weights, message):
    with pytest.raises(ValueError, match=message):
        build_ledger(symbolic="PASS", weights=weights)


def test_custom_weights_are_normalized_only_for_scored_evidence():
    out = build_ledger(symbolic="PASS", numerical="FAIL", weights={"symbolic": 0.8, "numerical": 0.2})
    assert out.scored_weight == pytest.approx(1.0)
    assert out.confidence == pytest.approx(0.8)
    assert out.total_weight == pytest.approx(1.5)


@pytest.mark.parametrize("alias", ["XVAL", "cross-validation", "crossvalidation", "CROSS_VALIDATION"])
def test_cross_validation_aliases_have_identical_meaning(alias):
    ledger = build_ledger(**{alias: "PASS"})
    assert ledger.entries["cross_validation"].status is ValidationStatus.PASS


def test_duplicate_aliases_never_replace_explicit_evidence():
    with pytest.raises(ValueError, match="iki kez"):
        build_ledger(cross_validation="FAIL", XVAL="PASS")


@pytest.mark.parametrize("value", ["not-a-status", {"status": "not-a-status"}, {"status": None}])
def test_unknown_status_never_becomes_pass_or_warning(value):
    with pytest.raises(ValueError):
        build_ledger(symbolic=value)


@pytest.mark.parametrize("value", [{"reason": "looks okay"}, {"score": 1.0}, None])
def test_statusless_input_is_unverified_and_never_fabricated(value):
    report = build_ledger(symbolic=value)
    assert report.entries["symbolic"].status is ValidationStatus.UNVERIFIED
    assert report.entries["symbolic"].score is None
    assert report.confidence == 0.0


class BrokenScientificReport:
    def to_dict(self):
        raise RuntimeError("unavailable")


class NonEmptyScientificReport:
    def to_dict(self):
        return {"posterior": {"mean": 2.0}}


@pytest.mark.parametrize("report", [BrokenScientificReport(), NonEmptyScientificReport()])
def test_unreviewed_scientific_report_is_not_assumed_to_have_passed(report):
    result = build_ledger(uncertainty=report)
    assert result.entries["uncertainty"].status is ValidationStatus.UNVERIFIED
    assert result.confidence == 0.0
    assert math.isfinite(result.confidence)
