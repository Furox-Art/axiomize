"""Independent method and refinement gates must never certify undefined values."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.numerical_verification import _relative_errors
from axiomize.validation.cross import compare_values
from axiomize.validation.status import ValidationStatus


@pytest.mark.parametrize("tolerance", [math.nan, math.inf, -math.inf, -0.1])
def test_invalid_cross_method_tolerances_are_rejected(tolerance: float) -> None:
    with pytest.raises(ValueError, match="tolerance must be finite and non-negative"):
        compare_values(1.0, 2.0, tolerance)


@pytest.mark.parametrize(
    ("primary", "verification"),
    [(math.nan, 1.0), (math.inf, 1.0), (1.0, -math.inf)],
)
def test_nonfinite_cross_method_outputs_are_rejected(primary: float, verification: float) -> None:
    with pytest.raises(ValueError, match="outputs must be finite"):
        compare_values(primary, verification, 0.01)


def test_cross_method_difference_overflow_is_not_pass() -> None:
    with pytest.raises(ValueError, match="difference overflowed"):
        compare_values(1e308, -1e308, 1e307)


def test_cross_method_regular_pass_and_conflict_remain_compatible() -> None:
    assert compare_values(1.0, 1.0 + 1e-5, 0.001).status is ValidationStatus.PASS
    assert compare_values(1.0, 2.0, 0.001).status is ValidationStatus.CONFLICT


@pytest.mark.parametrize(
    ("reference", "candidate"),
    [
        ([0.0], [math.nan]),
        ([0.0], [math.inf]),
        ([1e308], [-1e308]),
    ],
)
def test_refinement_rejects_nonfinite_or_overflowed_differences(
    reference: list[float], candidate: list[float],
) -> None:
    with pytest.raises(ValueError, match="finite arrays|difference overflowed"):
        _relative_errors(np.asarray(reference), np.asarray(candidate))


def test_identical_large_finite_refinement_arrays_have_zero_error() -> None:
    numbers = np.array([1e308, 1e308], dtype=float)
    assert _relative_errors(numbers, numbers) == (0.0, 0.0, 0.0)


def test_normal_finite_refinement_discrepancy_has_expected_metrics() -> None:
    abs_l2, rel_l2, rel_linf = _relative_errors(np.array([3.0, 4.0]), np.array([4.0, 5.0]))
    assert abs_l2 == pytest.approx(1.0)
    assert rel_l2 == pytest.approx(1.0 / math.sqrt(12.5))
    assert rel_linf == pytest.approx(0.25)


@pytest.mark.parametrize(
    ("reference", "candidate"),
    [(np.array([]), np.array([])), (np.array([1.0]), np.array([1.0, 2.0]))],
)
def test_missing_or_mismatched_refinement_vectors_rejected(
    reference: np.ndarray, candidate: np.ndarray
) -> None:
    with pytest.raises(ValueError):
        _relative_errors(reference, candidate)
