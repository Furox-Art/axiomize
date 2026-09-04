"""GAP-3 confidence ledger testleri."""

from axiomize.uncertainty.quantify import UncertaintyReport
from axiomize.validation.ledger import build_ledger
from axiomize.validation.status import ValidationStatus


def test_all_pass_high_score():
    ledger = build_ledger(
        symbolic=ValidationStatus.PASS,
        numerical=ValidationStatus.PASS,
        cross_validation=ValidationStatus.PASS,
        falsification=ValidationStatus.PASS,
        uncertainty={"status": ValidationStatus.PASS},
    )
    assert ledger.overall_status is ValidationStatus.PASS
    assert ledger.confidence >= 0.9
    assert all(e.status is ValidationStatus.PASS for e in ledger.entries.values())


def test_single_fail_low_score():
    ledger = build_ledger(
        symbolic=ValidationStatus.PASS,
        numerical=ValidationStatus.PASS,
        cross_validation=ValidationStatus.PASS,
        falsification=ValidationStatus.FAIL,
        uncertainty=ValidationStatus.PASS,
    )
    assert ledger.overall_status is ValidationStatus.FAIL
    assert ledger.confidence < 0.85
    assert ledger.entries["falsification"].status is ValidationStatus.FAIL


def test_missing_inputs_are_unverified():
    ledger = build_ledger(symbolic=ValidationStatus.PASS)
    assert ledger.entries["numerical"].status is ValidationStatus.UNVERIFIED
    assert ledger.entries["cross_validation"].status is ValidationStatus.UNVERIFIED
    assert ledger.entries["falsification"].status is ValidationStatus.UNVERIFIED
    assert ledger.entries["uncertainty"].status is ValidationStatus.UNVERIFIED
    assert ledger.overall_status is ValidationStatus.UNVERIFIED
    # Skor yalnizca verilen girdiden uretilir, eksikler paydaya katilmaz.
    assert ledger.confidence == 1.0


def test_raw_uncertainty_report_is_not_fabricated():
    ledger = build_ledger(
        symbolic=ValidationStatus.PASS,
        numerical=ValidationStatus.PASS,
        cross_validation=ValidationStatus.PASS,
        falsification=ValidationStatus.PASS,
        uncertainty=UncertaintyReport(parameter={"a": 1}),
    )
    assert ledger.entries["uncertainty"].status is ValidationStatus.UNVERIFIED
    assert ledger.overall_status is ValidationStatus.UNVERIFIED
