"""No silent coercion, nonfinite measurement repair, or hidden data deletion."""

from __future__ import annotations

import math

import pytest

from axiomize.data.quality import _robust_outlier_indices, clean_numeric_xy
from axiomize.limits import (
    MAX_ARRAY_ITEMS,
    MAX_INTEGER_DIGITS,
    bounded_float,
    bounded_int,
    bounded_sequence,
    enforce_finite_values,
    enforce_result_cells,
)


@pytest.mark.parametrize(
    ("input_value", "expected"),
    [
        (0, 0),
        (10, 10),
        (1.0, 1),
        ("  +12 ", 12),
        ("-5", -5),
    ],
)
def test_exact_integer_limits_preserve_declared_values(input_value, expected):
    assert bounded_int(input_value, name="sample", minimum=-10, maximum=20) == expected


@pytest.mark.parametrize(
    ("value", "pattern"),
    [
        (True, "boolean"),
        (1.2, "exact finite integer"),
        (float("nan"), "exact finite integer"),
        (float("inf"), "exact finite integer"),
        ("1.0", "must be an integer"),
        ("invalid", "must be an integer"),
        ("9" * (MAX_INTEGER_DIGITS + 1), "integer text exceeds"),
        ([], "must be an integer"),
        (-1, "between 0 and 10"),
        (11, "between 0 and 10"),
    ],
)
def test_integer_budget_cannot_truncate_or_accept_unbounded_numbers(value, pattern):
    with pytest.raises(ValueError, match=pattern):
        bounded_int(value, name="budget", minimum=0, maximum=10)


@pytest.mark.parametrize(
    ("value", "pattern"),
    [
        (True, "boolean"),
        (None, "numeric"),
        ("nonnumeric", "numeric"),
        (float("nan"), "finite"),
        (float("inf"), "finite"),
        (-0.1, ">= 0"),
        (2.0, "<= 1"),
    ],
)
def test_finite_float_budget_refuses_nonfinite_and_outside_bounds(value, pattern):
    with pytest.raises(ValueError, match=pattern):
        bounded_float(value, name="probability", minimum=0.0, maximum=1.0)


def test_strict_float_minimum_can_refuse_equal_boundary():
    with pytest.raises(ValueError, match="must be > 0"):
        bounded_float(0.0, name="positive", minimum=0.0, minimum_inclusive=False)
    assert bounded_float(0.5, name="positive", minimum=0.0, minimum_inclusive=False) == 0.5


@pytest.mark.parametrize(
    ("seq", "pattern"),
    [
        ("abc", "array"),
        ({"n": 2}, "array"),
        ([1], "length"),
        ([1, 2, 3, 4], "length"),
    ],
)
def test_bounded_sequence_never_assumes_arbitrary_iterable_is_observation_data(seq, pattern):
    with pytest.raises(ValueError, match=pattern):
        bounded_sequence(seq, name="series", minimum=2, maximum=3)


def test_result_array_cells_limit_product_not_only_individual_dimensions():
    enforce_result_cells(100, 100, 100, name="tensor")
    with pytest.raises(ValueError, match="numeric cells"):
        enforce_result_cells(100, 100, 1000 + 1, name="tensor")
    with pytest.raises(ValueError, match="dimension"):
        enforce_result_cells(-1, 3, name="tensor")


@pytest.mark.parametrize(
    ("values", "pattern"),
    [
        ([True], "boolean"),
        ([1.0, "bad"], "numeric"),
        ([0.0, float("nan")], "finite"),
        ([0.0, float("inf")], "finite"),
    ],
)
def test_derived_values_cannot_hide_nonfinite_observations(values, pattern):
    with pytest.raises(ValueError, match=pattern):
        enforce_finite_values(values, name="measurement")


def test_empty_or_positive_finite_values_are_safe_without_hidden_substitution():
    enforce_finite_values([], name="values")
    enforce_finite_values([0.0, -1.25, "3.5"], name="values")


@pytest.mark.parametrize(
    ("t", "y", "pattern"),
    [
        ([0.0], [1.0], "between 2"),
        ([0.0, 1.0], [1.0], "same length"),
        ([[0.0, 1.0], [2.0, 3.0]], [1.0, 2.0], "one-dimensional"),
        (["invalid", 1.0], [1.0, 2.0], "must be numeric"),
        ([0.0, 1.0], [1.0, 2.0], "duplicate_policy"),
    ],
)
def test_clean_numeric_data_rejects_structural_mismatches(t, y, pattern):
    kwargs = {"duplicate_policy": "invalid"} if pattern == "duplicate_policy" else {}
    with pytest.raises(ValueError, match=pattern):
        clean_numeric_xy(t, y, **kwargs)


def test_quality_cleaner_is_idempotent_on_already_valid_observations():
    a = clean_numeric_xy([0.0, 1.0, 2.0], [1.0, 2.0, 3.0])
    b = clean_numeric_xy(a.cleaned_t, a.cleaned_y)
    assert a.cleaned_t == b.cleaned_t
    assert a.cleaned_y == b.cleaned_y
    assert a.material_change is False
    assert b.material_change is False


def test_cleaner_drops_nonfinite_only_with_audit_and_explicit_opt_in():
    t = [0.0, 1.0, 2.0, 3.0, 4.0]
    y = [1.0, 2.0, float("nan"), 4.0, 5.0]
    with pytest.raises(ValueError, match="non-finite observations"):
        clean_numeric_xy(t, y, drop_nonfinite=False)
    result = clean_numeric_xy(t, y, drop_nonfinite=True)
    assert result.cleaned_t == [0.0, 1.0, 3.0, 4.0]
    assert result.cleaned_y == [1.0, 2.0, 4.0, 5.0]
    assert result.audit[0]["operation"] == "drop_nonfinite_rows"
    assert result.audit[0]["rows"] == [2]
    assert result.material_change is True


def test_cleaning_refuses_when_fewer_than_two_valid_observations_remain():
    with pytest.raises(ValueError, match="fewer than two finite"):
        clean_numeric_xy([0.0, 1.0, 2.0], [float("nan"), 1.0, float("inf")])


@pytest.mark.parametrize(
    ("policy", "expected_y"),
    [
        ("mean", [20.0, 10.0]),
        ("first", [10.0, 10.0]),
    ],
)
def test_duplicate_merging_preserves_original_time_order_without_sorting(policy, expected_y):
    result = clean_numeric_xy([2.0, 1.0, 2.0], [10.0, 10.0, 30.0], duplicate_policy=policy, sort_time=False)
    assert result.cleaned_t == [2.0, 1.0]
    assert result.cleaned_y == expected_y
    audit = next(a for a in result.audit if a["operation"] == "merge_duplicate_times")
    assert audit["order_policy"] == "first_occurrence"


def test_duplicate_merging_sorted_mode_is_explicit_and_auditable():
    result = clean_numeric_xy([2.0, 1.0, 2.0], [10.0, 10.0, 30.0], duplicate_policy="mean", sort_time=True)
    assert result.cleaned_t == [1.0, 2.0]
    assert result.cleaned_y == [10.0, 20.0]
    assert any(a["operation"] == "sort_by_time" for a in result.audit)


def test_duplicate_error_mode_does_not_change_the_original_measurements():
    with pytest.raises(ValueError, match="duplicate time coordinates"):
        clean_numeric_xy([0.0, 1.0, 1.0], [1.0, 2.0, 3.0], duplicate_policy="error")


def test_possible_data_outliers_are_flagged_not_removed():
    t = list(range(8))
    y = [1.0, 1.1, 1.2, 1.1, 1.0, 1.2, 1.1, 500.0]
    result = clean_numeric_xy(t, y)
    assert len(result.cleaned_y) == len(y)
    assert result.cleaned_y[-1] == 500.0
    assert any("outliers retained" in w for w in result.warnings)
    assert _robust_outlier_indices(__import__("numpy").array(y)) == [7]


def test_constant_small_samples_do_not_claim_robust_outlier_detection():
    import numpy as np

    assert _robust_outlier_indices(np.array([1.0, 1.0, 1.0, 1.0])) == []
    assert _robust_outlier_indices(np.array([1.0, 1.0, 1.0, 1.0, 1.0])) == []


def test_very_large_invalid_observation_vector_is_rejected_before_allocation():
    with pytest.raises(ValueError, match="hard observation limit"):
        clean_numeric_xy([0.0] * (MAX_ARRAY_ITEMS + 1), [1.0] * (MAX_ARRAY_ITEMS + 1))


def test_cleaned_series_must_remain_finite():
    result = clean_numeric_xy([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert all(math.isfinite(x) for x in result.cleaned_y)
